"""Runtime loading and inference for persisted forecasting model artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import pickle
from pathlib import Path
from typing import Any

from capm.domains.market_data import interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc
from capm.domains.prediction import StatisticalPredictionInput, TabularPredictionInput
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.training.sequence_dataset import (
    FeatureScaler,
    build_sequence_prediction_input,
    target_to_price,
)


@dataclass(frozen=True, slots=True)
class RuntimePrediction:
    """One production-runtime prediction result."""

    artifact_path: str
    artifact_kind: str
    model_name: str
    symbol: str
    interval: str
    reference_time: datetime
    prediction_time: datetime
    reference_value: float
    predicted_value: float
    predicted_return: float
    forecast_horizon: int
    target_mode: str
    feature_names: tuple[str, ...]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable prediction payload."""
        payload = asdict(self)
        payload["reference_time"] = self.reference_time.isoformat()
        payload["prediction_time"] = self.prediction_time.isoformat()
        payload["feature_names"] = list(self.feature_names)
        return payload


@dataclass(slots=True)
class PredictionRuntimeService:
    """Load persisted model artifacts and run one forecast against DB-backed data."""

    repository: TimescaleMarketDataRepository

    def predict(
        self,
        *,
        artifact_path: str | Path,
        symbol: str,
        interval: str,
        reference_time: datetime | None = None,
    ) -> RuntimePrediction:
        """Run one prediction from a persisted model artifact."""
        resolved_artifact_path = Path(artifact_path)
        payload = self._read_pickle(resolved_artifact_path)
        normalized_symbol = normalize_symbol(symbol)

        if self._is_deep_learning_payload(payload):
            return self._predict_deep_learning_sequence(
                payload=payload,
                artifact_path=resolved_artifact_path,
                symbol=normalized_symbol,
                interval=interval,
                reference_time=reference_time,
            )
        if self._is_production_tabular_payload(payload):
            return self._predict_production_tabular(
                payload=payload,
                artifact_path=resolved_artifact_path,
                symbol=normalized_symbol,
                interval=interval,
                reference_time=reference_time,
            )
        if self._is_walk_forward_payload(payload):
            return self._predict_walk_forward_model(
                payload=payload,
                artifact_path=resolved_artifact_path,
                symbol=normalized_symbol,
                interval=interval,
                reference_time=reference_time,
            )
        raise ValueError("Unsupported model artifact payload. Expected production model.pkl or trained_models.pkl.")

    @staticmethod
    def _read_pickle(path: Path) -> Any:
        if not path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {path}")
        with path.open("rb") as artifact_file:
            return pickle.load(artifact_file)

    @staticmethod
    def _is_production_tabular_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and {"model", "feature_names", "target_mode", "forecast_horizon"} <= set(
            payload
        )

    @staticmethod
    def _is_walk_forward_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("models"), list) and bool(payload["models"])

    @staticmethod
    def _is_deep_learning_payload(payload: Any) -> bool:
        return isinstance(payload, dict) and payload.get("artifact_kind") == "deep_learning_sequence"

    def _predict_deep_learning_sequence(
        self,
        *,
        payload: dict[str, Any],
        artifact_path: Path,
        symbol: str,
        interval: str,
        reference_time: datetime | None,
    ) -> RuntimePrediction:
        model = payload["model"]
        model_name = str(payload.get("model_name", getattr(model, "name", "unknown")))
        feature_names = tuple(str(name) for name in payload["feature_names"])
        forecast_horizon = int(payload["forecast_horizon"])
        sequence_length = int(payload["sequence_length"])
        target_mode = str(payload.get("target_mode", "price"))
        target_field = str(payload.get("target_field", "close"))
        scaler = FeatureScaler.from_payload(dict(payload["scaler"]))
        rows = self._load_feature_window(
            symbol=symbol,
            interval=interval,
            reference_time=reference_time,
            window_size=sequence_length,
            required_features=feature_names,
        )
        prediction_input = build_sequence_prediction_input(
            rows=rows,
            feature_names=feature_names,
            forecast_horizon=forecast_horizon,
            target_field=target_field,
            scaler=scaler,
        )
        predicted_target, detail = model.predict(prediction_input)
        predicted_value = target_to_price(prediction_input.reference_value, float(predicted_target), target_mode)
        return RuntimePrediction(
            artifact_path=str(artifact_path),
            artifact_kind="deep_learning_sequence",
            model_name=model_name,
            symbol=symbol,
            interval=interval,
            reference_time=prediction_input.reference_time,
            prediction_time=prediction_input.prediction_time,
            reference_value=prediction_input.reference_value,
            predicted_value=predicted_value,
            predicted_return=(predicted_value - prediction_input.reference_value) / prediction_input.reference_value,
            forecast_horizon=forecast_horizon,
            target_mode=target_mode,
            feature_names=feature_names,
            metadata={
                "target_field": target_field,
                "sequence_length": sequence_length,
                "trained_through": payload.get("trained_through"),
                "predict_detail": detail,
            },
        )

    def _predict_production_tabular(
        self,
        *,
        payload: dict[str, Any],
        artifact_path: Path,
        symbol: str,
        interval: str,
        reference_time: datetime | None,
    ) -> RuntimePrediction:
        model = payload["model"]
        model_name = str(payload.get("model_name", getattr(model, "name", "unknown")))
        feature_names = tuple(str(name) for name in payload["feature_names"])
        forecast_horizon = int(payload["forecast_horizon"])
        target_mode = str(payload.get("target_mode", "price"))
        target_field = str(payload.get("target_field", "close"))

        row = self._load_feature_row(
            symbol=symbol,
            interval=interval,
            reference_time=reference_time,
            required_features=feature_names,
        )
        reference_value = float(getattr(row.candle, target_field))
        prediction_time = row.open_time + (interval_to_timedelta(interval) * forecast_horizon)
        predicted_target, detail = model.predict(
            TabularPredictionInput(
                reference_time=row.open_time,
                prediction_time=prediction_time,
                reference_value=reference_value,
                feature_names=feature_names,
                feature_vector=tuple(float(row.indicator_values[name]) for name in feature_names),
                forecast_horizon=forecast_horizon,
            )
        )
        predicted_value = self._target_to_price(reference_value, float(predicted_target), target_mode)
        return RuntimePrediction(
            artifact_path=str(artifact_path),
            artifact_kind="production_tabular",
            model_name=model_name,
            symbol=symbol,
            interval=interval,
            reference_time=row.open_time,
            prediction_time=prediction_time,
            reference_value=reference_value,
            predicted_value=predicted_value,
            predicted_return=(predicted_value - reference_value) / reference_value,
            forecast_horizon=forecast_horizon,
            target_mode=target_mode,
            feature_names=feature_names,
            metadata={
                "target_field": target_field,
                "trained_through": payload.get("trained_through"),
                "predict_detail": detail,
            },
        )

    def _predict_walk_forward_model(
        self,
        *,
        payload: dict[str, Any],
        artifact_path: Path,
        symbol: str,
        interval: str,
        reference_time: datetime | None,
    ) -> RuntimePrediction:
        entry = payload["models"][-1]
        model = entry["model"]
        model_name = str(entry.get("model_name", getattr(model, "name", "unknown")))
        forecast_horizon = self._infer_walk_forward_horizon(entry, interval=interval)
        row = self._load_candle(symbol=symbol, interval=interval, reference_time=reference_time)
        prediction_time = row.open_time + (interval_to_timedelta(interval) * forecast_horizon)
        reference_value = float(row.close)
        predicted_value, detail = model.predict(
            StatisticalPredictionInput(
                reference_time=row.open_time,
                prediction_time=prediction_time,
                reference_value=reference_value,
                forecast_horizon=forecast_horizon,
                interval=interval,
            )
        )
        return RuntimePrediction(
            artifact_path=str(artifact_path),
            artifact_kind="walk_forward_latest_model",
            model_name=model_name,
            symbol=symbol,
            interval=interval,
            reference_time=row.open_time,
            prediction_time=prediction_time,
            reference_value=reference_value,
            predicted_value=float(predicted_value),
            predicted_return=(float(predicted_value) - reference_value) / reference_value,
            forecast_horizon=forecast_horizon,
            target_mode="price",
            feature_names=(),
            metadata={
                "saved_model_scope": payload.get("saved_model_scope"),
                "split_id": entry.get("split_id"),
                "artifact_latest_reference_time": entry.get("latest_reference_time"),
                "artifact_latest_prediction_time": entry.get("latest_prediction_time"),
                "predict_detail": detail,
            },
        )

    @staticmethod
    def _target_to_price(reference_value: float, predicted_target: float, target_mode: str) -> float:
        if target_mode == "price":
            return predicted_target
        if target_mode == "return":
            return reference_value * (1 + predicted_target)
        raise ValueError("Unsupported model artifact target_mode. Expected 'price' or 'return'.")

    def _load_feature_row(
        self,
        *,
        symbol: str,
        interval: str,
        reference_time: datetime | None,
        required_features: tuple[str, ...],
    ):
        if reference_time is None:
            window = self.repository.get_latest_complete_window(symbol, interval, 1, required_features)
            if window is None or not window.rows:
                raise ValueError("No latest feature row is available for prediction.")
            row = window.rows[-1]
        else:
            start = ensure_utc(reference_time)
            rows = self.repository.get_feature_rows(symbol, interval, start, start + interval_to_timedelta(interval))
            if not rows:
                raise ValueError(f"No feature row is available at {start.isoformat()}.")
            row = rows[0]

        missing = tuple(name for name in required_features if row.indicator_values.get(name) is None)
        if not row.is_feature_ready or missing:
            raise ValueError(
                "Feature row is not ready for prediction. "
                f"reference_time={row.open_time.isoformat()}, missing_features={list(missing)}"
            )
        return row

    def _load_feature_window(
        self,
        *,
        symbol: str,
        interval: str,
        reference_time: datetime | None,
        window_size: int,
        required_features: tuple[str, ...],
    ):
        if reference_time is None:
            window = self.repository.get_latest_complete_window(symbol, interval, window_size, required_features)
            if window is None or not window.rows:
                raise ValueError("No latest feature window is available for prediction.")
            if not window.is_complete:
                raise ValueError(f"Latest feature window is incomplete: {window.gap_reason}")
            return tuple(window.rows)

        end = ensure_utc(reference_time) + interval_to_timedelta(interval)
        start = end - (interval_to_timedelta(interval) * window_size)
        rows = tuple(self.repository.get_feature_rows(symbol, interval, start, end))
        if len(rows) != window_size:
            raise ValueError(
                f"No complete feature window ending at {ensure_utc(reference_time).isoformat()} "
                f"with window_size={window_size}."
            )
        missing = [
            name
            for row in rows
            for name in required_features
            if not row.is_feature_ready or row.indicator_values.get(name) is None
        ]
        if missing:
            raise ValueError(f"Feature window is not ready for prediction. missing_features={sorted(set(missing))}")
        return rows

    def _load_candle(self, *, symbol: str, interval: str, reference_time: datetime | None):
        if reference_time is None:
            latest = self.repository.get_latest_candle_time(symbol, interval)
            if latest is None:
                raise ValueError("No latest candle is available for prediction.")
            reference_time = latest
        start = ensure_utc(reference_time)
        rows = self.repository.get_candles(symbol, interval, start, start + interval_to_timedelta(interval))
        if not rows:
            raise ValueError(f"No candle is available at {start.isoformat()}.")
        return rows[0]

    @staticmethod
    def _infer_walk_forward_horizon(entry: dict[str, Any], *, interval: str) -> int:
        latest_reference = entry.get("latest_reference_time")
        latest_prediction = entry.get("latest_prediction_time")
        if isinstance(latest_reference, str) and isinstance(latest_prediction, str):
            reference = ensure_utc(datetime.fromisoformat(latest_reference))
            prediction = ensure_utc(datetime.fromisoformat(latest_prediction))
            delta = prediction - reference
            interval_seconds = interval_to_timedelta(interval).total_seconds()
            if delta.total_seconds() > 0 and interval_seconds > 0:
                return max(1, int(delta.total_seconds() / interval_seconds))
        return 1
