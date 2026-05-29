"""Production-style training for deep-learning sequence models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, Callable

from capm.domains.features import FeatureRow
from capm.domains.market_data import normalize_symbol
from capm.domains.market_data.entities import ensure_utc
from capm.domains.prediction import BacktestReport, ForecastResult, ThresholdSignalPolicy, direction_accuracy, mape, rmse
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.models import create_model, get_model_family
from capm.services.backtesting import BacktraderBacktestRunner
from capm.services.training.artifact_store import LocalArtifactStore
from capm.services.training.sequence_dataset import (
    FeatureScaler,
    build_array_sequence_dataset,
    infer_ready_feature_names,
    fit_feature_scaler_from_rows,
    target_to_price,
)


@dataclass(frozen=True, slots=True)
class DeepLearningTrainingResult:
    """Summary of one deep-learning training run."""

    run_id: str
    model_name: str
    symbol: str
    interval: str
    target_mode: str
    sequence_length: int
    feature_names: tuple[str, ...]
    train_samples: int
    holdout_predictions: int
    rmse: float
    mape: float
    direction_accuracy: float
    fit_duration_seconds: float
    predict_duration_seconds: float
    model_artifact_path: str
    summary_artifact_path: str
    backtest: BacktestReport


def _ready_rows(rows: list[FeatureRow]) -> tuple[FeatureRow, ...]:
    return tuple(row for row in rows if row.is_feature_ready)


def _noop_progress(_message: str) -> None:
    return None


@dataclass(slots=True)
class DeepLearningProductionTrainer:
    """Train one LSTM/GRU sequence model artifact and evaluate a holdout period."""

    repository: TimescaleMarketDataRepository
    artifact_store: LocalArtifactStore

    def train_sequence_model(
        self,
        *,
        symbol: str,
        interval: str,
        model_name: str,
        start_time: datetime,
        split_time: datetime,
        end_time: datetime,
        sequence_length: int,
        forecast_horizon: int,
        target_field: str = "close",
        target_mode: str = "return",
        scaler_mode: str = "zscore",
        model_parameters: dict[str, Any] | None = None,
        required_features: tuple[str, ...] = (),
        starting_cash: float = 10_000.0,
        buy_threshold: float = 0.001,
        commission_rate: float = 0.001,
        cash_fraction: float = 0.95,
        progress_callback: Callable[[str], None] | None = None,
    ) -> DeepLearningTrainingResult:
        """Train, holdout-test, backtest, and persist one sequence model."""
        progress = progress_callback or _noop_progress
        if get_model_family(model_name) != "deep_learning":
            raise ValueError("Deep-learning trainer supports LSTM and GRU only.")
        if sequence_length < 1:
            raise ValueError("sequence_length must be positive.")
        if forecast_horizon < 1:
            raise ValueError("forecast_horizon must be positive.")
        if target_mode not in {"price", "return"}:
            raise ValueError("target_mode must be either 'price' or 'return'.")

        normalized_symbol = normalize_symbol(symbol)
        normalized_start = ensure_utc(start_time)
        normalized_split = ensure_utc(split_time)
        normalized_end = ensure_utc(end_time)
        if not normalized_start < normalized_split < normalized_end:
            raise ValueError("Expected start_time < split_time < end_time.")

        progress(
            "loading feature rows "
            f"symbol={normalized_symbol} interval={interval} "
            f"start={normalized_start.isoformat()} end={normalized_end.isoformat()}"
        )
        rows = _ready_rows(
            self.repository.get_feature_rows(normalized_symbol, interval, normalized_start, normalized_end)
        )
        progress(f"loaded ready feature rows: {len(rows):,}")
        if len(rows) <= sequence_length + forecast_horizon:
            raise ValueError("Not enough ready feature rows for deep-learning training.")
        feature_names = required_features or infer_ready_feature_names(rows)
        progress(f"using features: {', '.join(feature_names)}")
        split_index = next((index for index, row in enumerate(rows) if row.open_time >= normalized_split), len(rows))
        holdout_candidate_count = max(len(rows) - split_index - forecast_horizon, 0)
        progress(
            f"split rows: train_candidates={split_index:,} "
            f"holdout_candidates={holdout_candidate_count:,} sequence_length={sequence_length}"
        )
        if split_index < sequence_length:
            raise ValueError("Split leaves no sequence training data.")
        if split_index + forecast_horizon >= len(rows):
            raise ValueError("Split leaves no holdout data with the requested horizon.")

        progress(f"fitting scaler mode={scaler_mode}")
        scaler = fit_feature_scaler_from_rows(rows[:split_index], feature_names=feature_names, mode=scaler_mode)
        progress("building compact training sequence index")
        train_dataset = build_array_sequence_dataset(
            rows=rows,
            feature_names=feature_names,
            sequence_length=sequence_length,
            forecast_horizon=forecast_horizon,
            target_field=target_field,
            target_mode=target_mode,
            start_index=0,
            end_index=split_index,
            scaler=scaler,
        )
        progress(f"built training samples: {len(train_dataset.target_values):,}")
        progress("building compact holdout sequence index")
        holdout_dataset = build_array_sequence_dataset(
            rows=rows,
            feature_names=feature_names,
            sequence_length=sequence_length,
            forecast_horizon=forecast_horizon,
            target_field=target_field,
            target_mode=target_mode,
            start_index=split_index,
            end_index=len(rows) - forecast_horizon,
            scaler=scaler,
        )
        progress(f"built holdout samples: {len(holdout_dataset.target_values):,}")

        resolved_model_parameters = dict(model_parameters or {})
        resolved_model_parameters["progress_callback"] = progress
        model = create_model(model_name, resolved_model_parameters)
        progress(f"fitting {model_name} model")
        fit_started = perf_counter()
        if hasattr(model, "fit_array_dataset"):
            fit_detail = model.fit_array_dataset(train_dataset)
        else:
            raise ValueError("Deep-learning model does not support array-backed training.")
        if hasattr(model, "model_kwargs"):
            model.model_kwargs.pop("progress_callback", None)
        fit_duration = perf_counter() - fit_started
        progress(f"fit complete in {fit_duration:.2f}s")

        predict_started = perf_counter()
        progress(f"predicting holdout samples in batches: {len(holdout_dataset.target_values):,}")
        batch_size = int(resolved_model_parameters.get("batch_size", 512))
        predicted_targets = model.predict_array_dataset(holdout_dataset, batch_size=batch_size)
        predict_duration = perf_counter() - predict_started
        reference_values = tuple(float(value) for value in holdout_dataset.reference_values)
        actual_values = tuple(float(value) for value in holdout_dataset.actual_values)
        predicted_values = tuple(
            target_to_price(reference_value, predicted_target, target_mode)
            for reference_value, predicted_target in zip(reference_values, predicted_targets, strict=True)
        )
        prediction_times = tuple(rows[int(index) + forecast_horizon].open_time for index in holdout_dataset.reference_indices)
        progress(
            f"holdout prediction complete valid={len(predicted_values):,} predict_time={predict_duration:.2f}s"
        )

        forecast_result = ForecastResult(
            symbol=normalized_symbol,
            interval=interval,
            model_name=model_name,
            prediction_times=tuple(prediction_times),
            predicted_values=predicted_values,
            actual_values=actual_values,
            forecast_horizon=forecast_horizon,
            metadata={
                "reference_values": list(reference_values),
                "split_time": normalized_split.isoformat(),
                "target_mode": target_mode,
            },
        )
        progress("running Backtrader holdout evaluation")
        backtest = BacktraderBacktestRunner(self.repository).run_from_forecast_result(
            symbol=normalized_symbol,
            interval=interval,
            start_time=normalized_split,
            end_time=normalized_end,
            forecast_result=forecast_result,
            starting_cash=starting_cash,
            signal_policy=ThresholdSignalPolicy(buy_threshold=buy_threshold),
            commission_rate=commission_rate,
            cash_fraction=cash_fraction,
        )
        progress(
            f"backtest complete cumulative_return={backtest.cumulative_return:.6f} "
            f"trades={backtest.trade_count}"
        )

        run_id = self._build_run_id(normalized_symbol, interval, model_name, forecast_horizon)
        progress(f"writing model artifact run_id={run_id}")
        model_artifact_path = self.artifact_store.write_pickle(
            run_id=run_id,
            relative_path="model.pkl",
            payload={
                "artifact_kind": "deep_learning_sequence",
                "model": model,
                "model_name": model_name,
                "model_parameters": dict(model_parameters or {}),
                "feature_names": feature_names,
                "sequence_length": sequence_length,
                "target_field": target_field,
                "target_mode": target_mode,
                "forecast_horizon": forecast_horizon,
                "scaler": scaler.to_payload(),
                "trained_through": rows[split_index - 1].open_time.isoformat(),
                "fit_detail": fit_detail,
            },
        )
        result = DeepLearningTrainingResult(
            run_id=run_id,
            model_name=model_name,
            symbol=normalized_symbol,
            interval=interval,
            target_mode=target_mode,
            sequence_length=sequence_length,
            feature_names=feature_names,
            train_samples=len(train_dataset.target_values),
            holdout_predictions=len(predicted_values),
            rmse=rmse(predicted_values, actual_values),
            mape=mape(predicted_values, actual_values),
            direction_accuracy=direction_accuracy(
                predicted_values=predicted_values,
                actual_values=actual_values,
                reference_values=reference_values,
            ),
            fit_duration_seconds=fit_duration,
            predict_duration_seconds=predict_duration,
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
                forecast_horizon=forecast_horizon,
                scaler=scaler,
                buy_threshold=buy_threshold,
                commission_rate=commission_rate,
                cash_fraction=cash_fraction,
                fit_detail=fit_detail,
            ),
        )
        progress(f"summary written: {summary_path}")
        return DeepLearningTrainingResult(
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
        return f"{started_at}_{symbol.lower()}_{interval}_{model_name}_dl_{forecast_horizon}steps"

    @staticmethod
    def _summary_payload(
        result: DeepLearningTrainingResult,
        *,
        start_time: datetime,
        split_time: datetime,
        end_time: datetime,
        forecast_horizon: int,
        scaler: FeatureScaler,
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
            "sequence_length": result.sequence_length,
            "forecast_horizon": forecast_horizon,
            "start_time": start_time.isoformat(),
            "split_time": split_time.isoformat(),
            "end_time": end_time.isoformat(),
            "feature_names": list(result.feature_names),
            "train_samples": result.train_samples,
            "holdout_predictions": result.holdout_predictions,
            "metrics": {
                "rmse": result.rmse,
                "mape": result.mape,
                "direction_accuracy": result.direction_accuracy,
                "fit_duration_seconds": result.fit_duration_seconds,
                "predict_duration_seconds": result.predict_duration_seconds,
            },
            "backtest": asdict(result.backtest),
            "signal_policy": {
                "buy_threshold": buy_threshold,
                "commission_rate": commission_rate,
                "cash_fraction": cash_fraction,
            },
            "scaler": scaler.to_payload(),
            "fit_detail": fit_detail,
            "model_artifact_path": result.model_artifact_path,
        }
