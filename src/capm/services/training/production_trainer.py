"""Production-style model training and holdout backtesting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from capm.domains.features import FeatureRow
from capm.domains.market_data import interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc
from capm.domains.prediction import (
    BacktestReport,
    ForecastResult,
    TabularPredictionInput,
    TabularTrainingInput,
    ThresholdSignalPolicy,
    direction_accuracy,
    mape,
    rmse,
)
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.models import create_model, get_model_family
from capm.services.backtesting import BacktraderBacktestRunner
from capm.services.training.adapters import infer_feature_names
from capm.services.training.artifact_store import LocalArtifactStore


@dataclass(frozen=True, slots=True)
class ProductionTrainingResult:
    """Summary of one production-style training run."""

    run_id: str
    model_name: str
    symbol: str
    interval: str
    target_mode: str
    feature_names: tuple[str, ...]
    train_rows: int
    calibration_predictions: int
    holdout_predictions: int
    calibrated_buy_threshold: float
    rmse: float
    mape: float
    direction_accuracy: float
    fit_duration_seconds: float
    predict_duration_seconds: float
    final_fit_duration_seconds: float
    model_artifact_path: str
    summary_artifact_path: str
    backtest: BacktestReport


def _field_value(row: FeatureRow, target_field: str) -> float:
    return float(getattr(row.candle, target_field))


def _target_value(row: FeatureRow, target_row: FeatureRow, target_field: str, target_mode: str) -> float:
    reference_value = _field_value(row, target_field)
    future_value = _field_value(target_row, target_field)
    if target_mode == "price":
        return future_value
    if target_mode == "return":
        if reference_value == 0:
            raise ValueError("Cannot compute return target from a zero reference value.")
        return (future_value - reference_value) / reference_value
    raise ValueError("`target_mode` must be either 'price' or 'return'.")


def _forecast_price(reference_value: float, predicted_target: float, target_mode: str) -> float:
    if target_mode == "price":
        return predicted_target
    if target_mode == "return":
        return reference_value * (1 + predicted_target)
    raise ValueError("`target_mode` must be either 'price' or 'return'.")


def _ready_rows(rows: list[FeatureRow]) -> tuple[FeatureRow, ...]:
    return tuple(row for row in rows if row.is_feature_ready)


def _build_training_input(
    *,
    rows: tuple[FeatureRow, ...],
    feature_names: tuple[str, ...],
    target_field: str,
    target_mode: str,
    forecast_horizon: int,
    start_index: int,
    end_index: int,
) -> TabularTrainingInput:
    """Build aligned X/y rows for references in [start_index, end_index)."""
    timestamps: list[datetime] = []
    feature_matrix: list[tuple[float, ...]] = []
    target_values: list[float] = []
    for index in range(start_index, end_index):
        target_index = index + forecast_horizon
        if target_index >= len(rows):
            break
        row = rows[index]
        target_row = rows[target_index]
        timestamps.append(row.open_time)
        feature_matrix.append(tuple(float(row.indicator_values[name]) for name in feature_names))
        target_values.append(_target_value(row, target_row, target_field, target_mode))
    return TabularTrainingInput(
        timestamps=tuple(timestamps),
        feature_names=feature_names,
        feature_matrix=tuple(feature_matrix),
        target_values=tuple(target_values),
    )


@dataclass(slots=True)
class ProductionModelTrainer:
    """Train one tabular model artifact and evaluate it on a holdout period."""

    repository: TimescaleMarketDataRepository
    artifact_store: LocalArtifactStore

    def train_tabular_model(
        self,
        *,
        symbol: str,
        interval: str,
        model_name: str,
        start_time: datetime,
        split_time: datetime,
        end_time: datetime,
        forecast_horizon: int,
        target_field: str = "close",
        target_mode: str = "return",
        calibration_time: datetime | None = None,
        model_parameters: dict[str, Any] | None = None,
        required_features: tuple[str, ...] = (),
        starting_cash: float = 10_000.0,
        buy_threshold: float = 0.001,
        commission_rate: float = 0.001,
        cash_fraction: float = 0.95,
    ) -> ProductionTrainingResult:
        """Train a tabular model once, backtest holdout forecasts, then fit final model."""
        if get_model_family(model_name) != "ml":
            raise ValueError("Production trainer currently supports tabular ML models only.")
        if forecast_horizon < 1:
            raise ValueError("`forecast_horizon` must be positive.")

        normalized_symbol = normalize_symbol(symbol)
        normalized_start = ensure_utc(start_time)
        normalized_calibration = ensure_utc(calibration_time) if calibration_time is not None else None
        normalized_split = ensure_utc(split_time)
        normalized_end = ensure_utc(end_time)
        if not normalized_start < normalized_split < normalized_end:
            raise ValueError("Expected start_time < split_time < end_time.")
        if normalized_calibration is not None and not normalized_start < normalized_calibration < normalized_split:
            raise ValueError("Expected start_time < calibration_time < split_time.")
        if target_mode not in {"price", "return"}:
            raise ValueError("`target_mode` must be either 'price' or 'return'.")

        raw_rows = self.repository.get_feature_rows(
            normalized_symbol,
            interval,
            normalized_start,
            normalized_end,
        )
        rows = _ready_rows(raw_rows)
        if len(rows) <= forecast_horizon + 2:
            raise ValueError("Not enough ready feature rows for production training.")

        feature_names = required_features or infer_feature_names(rows)
        split_index = next((index for index, row in enumerate(rows) if row.open_time >= normalized_split), len(rows))
        calibration_index = (
            next((index for index, row in enumerate(rows) if row.open_time >= normalized_calibration), split_index)
            if normalized_calibration is not None
            else split_index
        )
        if split_index <= 1:
            raise ValueError("Split leaves no training data.")
        if calibration_index <= 1:
            raise ValueError("Calibration split leaves no training data.")
        if split_index + forecast_horizon >= len(rows):
            raise ValueError("Split leaves no holdout data with the requested horizon.")

        model_parameters = dict(model_parameters or {})
        calibrated_buy_threshold = buy_threshold
        calibration_predictions = 0
        if normalized_calibration is not None:
            calibration_model = create_model(model_name, model_parameters)
            calibration_train_input = _build_training_input(
                rows=rows,
                feature_names=feature_names,
                target_field=target_field,
                target_mode=target_mode,
                forecast_horizon=forecast_horizon,
                start_index=0,
                end_index=calibration_index,
            )
            calibration_model.fit(calibration_train_input)
            calibration_returns: list[float] = []
            for index in range(calibration_index, split_index - forecast_horizon):
                row = rows[index]
                target_row = rows[index + forecast_horizon]
                predicted_target, _ = calibration_model.predict(
                    TabularPredictionInput(
                        reference_time=row.open_time,
                        prediction_time=target_row.open_time,
                        reference_value=_field_value(row, target_field),
                        feature_names=feature_names,
                        feature_vector=tuple(float(row.indicator_values[name]) for name in feature_names),
                        forecast_horizon=forecast_horizon,
                    )
                )
                reference_value = _field_value(row, target_field)
                predicted_price = _forecast_price(reference_value, predicted_target, target_mode)
                calibration_returns.append((predicted_price - reference_value) / reference_value)
            calibration_predictions = len(calibration_returns)
            if calibration_returns:
                positive_returns = sorted(value for value in calibration_returns if value > commission_rate * 2)
                if positive_returns:
                    calibrated_buy_threshold = max(
                        buy_threshold,
                        positive_returns[int(len(positive_returns) * 0.75)],
                    )

        evaluation_model = create_model(model_name, model_parameters)
        train_input = _build_training_input(
            rows=rows,
            feature_names=feature_names,
            target_field=target_field,
            target_mode=target_mode,
            forecast_horizon=forecast_horizon,
            start_index=0,
            end_index=split_index,
        )
        fit_started = perf_counter()
        fit_detail = evaluation_model.fit(train_input)
        fit_duration = perf_counter() - fit_started

        predicted_values: list[float] = []
        actual_values: list[float] = []
        reference_values: list[float] = []
        prediction_times: list[datetime] = []
        predict_duration = 0.0
        for index in range(split_index, len(rows) - forecast_horizon):
            row = rows[index]
            target_row = rows[index + forecast_horizon]
            prediction_input = TabularPredictionInput(
                reference_time=row.open_time,
                prediction_time=target_row.open_time,
                reference_value=_field_value(row, target_field),
                feature_names=feature_names,
                feature_vector=tuple(float(row.indicator_values[name]) for name in feature_names),
                forecast_horizon=forecast_horizon,
            )
            predict_started = perf_counter()
            predicted_target, _predict_detail = evaluation_model.predict(prediction_input)
            predict_duration += perf_counter() - predict_started
            predicted_value = _forecast_price(prediction_input.reference_value, predicted_target, target_mode)
            predicted_values.append(predicted_value)
            actual_values.append(_field_value(target_row, target_field))
            reference_values.append(prediction_input.reference_value)
            prediction_times.append(target_row.open_time)

        forecast_result = ForecastResult(
            symbol=normalized_symbol,
            interval=interval,
            model_name=model_name,
            prediction_times=tuple(prediction_times),
            predicted_values=tuple(predicted_values),
            actual_values=tuple(actual_values),
            forecast_horizon=forecast_horizon,
            metadata={
                "reference_values": reference_values,
                "split_time": normalized_split.isoformat(),
                "target_mode": target_mode,
                "calibrated_buy_threshold": calibrated_buy_threshold,
            },
        )
        backtest = BacktraderBacktestRunner(self.repository).run_from_forecast_result(
            symbol=normalized_symbol,
            interval=interval,
            start_time=normalized_split,
            end_time=normalized_end,
            forecast_result=forecast_result,
            starting_cash=starting_cash,
            signal_policy=ThresholdSignalPolicy(buy_threshold=calibrated_buy_threshold),
            commission_rate=commission_rate,
            cash_fraction=cash_fraction,
        )

        final_model = create_model(model_name, model_parameters)
        final_train_input = _build_training_input(
            rows=rows,
            feature_names=feature_names,
            target_field=target_field,
            target_mode=target_mode,
            forecast_horizon=forecast_horizon,
            start_index=0,
            end_index=len(rows) - forecast_horizon,
        )
        final_fit_started = perf_counter()
        final_fit_detail = final_model.fit(final_train_input)
        final_fit_duration = perf_counter() - final_fit_started

        run_id = self._build_run_id(normalized_symbol, interval, model_name, forecast_horizon)
        model_artifact_path = self.artifact_store.write_pickle(
            run_id=run_id,
            relative_path="model.pkl",
            payload={
                "model": final_model,
                "model_name": model_name,
                "model_parameters": model_parameters,
                "feature_names": feature_names,
                "target_field": target_field,
                "target_mode": target_mode,
                "forecast_horizon": forecast_horizon,
                "trained_through": rows[-forecast_horizon - 1].open_time.isoformat(),
                "fit_detail": final_fit_detail,
            },
        )
        result = ProductionTrainingResult(
            run_id=run_id,
            model_name=model_name,
            symbol=normalized_symbol,
            interval=interval,
            target_mode=target_mode,
            feature_names=feature_names,
            train_rows=len(train_input.target_values),
            calibration_predictions=calibration_predictions,
            holdout_predictions=len(predicted_values),
            calibrated_buy_threshold=calibrated_buy_threshold,
            rmse=rmse(tuple(predicted_values), tuple(actual_values)),
            mape=mape(tuple(predicted_values), tuple(actual_values)),
            direction_accuracy=direction_accuracy(
                predicted_values=tuple(predicted_values),
                actual_values=tuple(actual_values),
                reference_values=tuple(reference_values),
            ),
            fit_duration_seconds=fit_duration,
            predict_duration_seconds=predict_duration,
            final_fit_duration_seconds=final_fit_duration,
            model_artifact_path=model_artifact_path,
            summary_artifact_path="",
            backtest=backtest,
        )
        summary_path = self.artifact_store.write_json(
            run_id=run_id,
            relative_path="summary.json",
            payload=self._summary_payload(
                result,
                start_time=normalized_start,
                split_time=normalized_split,
                end_time=normalized_end,
                buy_threshold=calibrated_buy_threshold,
                commission_rate=commission_rate,
                cash_fraction=cash_fraction,
                fit_detail=fit_detail,
            ),
        )
        return ProductionTrainingResult(
            **{
                **asdict(result),
                "summary_artifact_path": summary_path,
                "feature_names": tuple(result.feature_names),
                "backtest": backtest,
            }
        )

    @staticmethod
    def _build_run_id(symbol: str, interval: str, model_name: str, forecast_horizon: int) -> str:
        started_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{started_at}_{symbol.lower()}_{interval}_{model_name}_prod_{forecast_horizon}steps"

    @staticmethod
    def _summary_payload(
        result: ProductionTrainingResult,
        *,
        start_time: datetime,
        split_time: datetime,
        end_time: datetime,
        buy_threshold: float,
        commission_rate: float,
        cash_fraction: float,
        fit_detail: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "run_id": result.run_id,
            "model_name": result.model_name,
            "symbol": result.symbol,
            "interval": result.interval,
            "target_mode": result.target_mode,
            "start_time": start_time.isoformat(),
            "split_time": split_time.isoformat(),
            "end_time": end_time.isoformat(),
            "feature_names": list(result.feature_names),
            "train_rows": result.train_rows,
            "calibration_predictions": result.calibration_predictions,
            "holdout_predictions": result.holdout_predictions,
            "calibrated_buy_threshold": result.calibrated_buy_threshold,
            "metrics": {
                "rmse": result.rmse,
                "mape": result.mape,
                "direction_accuracy": result.direction_accuracy,
                "fit_duration_seconds": result.fit_duration_seconds,
                "predict_duration_seconds": result.predict_duration_seconds,
                "final_fit_duration_seconds": result.final_fit_duration_seconds,
            },
            "backtest": asdict(result.backtest),
            "signal_policy": {
                "buy_threshold": buy_threshold,
                "commission_rate": commission_rate,
                "cash_fraction": cash_fraction,
            },
            "fit_detail": fit_detail,
            "model_artifact_path": result.model_artifact_path,
        }
