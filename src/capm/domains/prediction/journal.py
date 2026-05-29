"""Prediction journal domain entities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from capm.domains.market_data import interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc

from .errors import PredictionValidationError


def prediction_direction(value: float) -> str:
    """Convert a numeric return into an up/down/flat direction."""
    if value > 0:
        return "up"
    if value < 0:
        return "down"
    return "flat"


@dataclass(frozen=True, slots=True)
class PredictionJournalEntry:
    """One persisted runtime prediction plus optional settlement fields."""

    id: int | None
    created_at: datetime | None
    updated_at: datetime | None
    symbol: str
    interval: str
    model_name: str
    artifact_kind: str
    artifact_path: str
    artifact_sha256: str
    reference_time: datetime
    prediction_time: datetime
    forecast_horizon: int
    target_field: str
    target_mode: str
    reference_value: float
    predicted_value: float
    predicted_return: float
    predicted_direction: str
    feature_names: tuple[str, ...]
    metadata: dict[str, Any]
    actual_value: float | None = None
    actual_return: float | None = None
    actual_direction: str | None = None
    absolute_error: float | None = None
    absolute_percentage_error: float | None = None
    direction_correct: bool | None = None
    settled_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_symbol = normalize_symbol(self.symbol)
        interval_to_timedelta(self.interval)
        normalized_model_name = self.model_name.strip().lower()
        normalized_artifact_kind = self.artifact_kind.strip()
        normalized_artifact_path = self.artifact_path.strip()
        normalized_artifact_sha = self.artifact_sha256.strip()
        normalized_target_field = self.target_field.strip().lower()
        normalized_target_mode = self.target_mode.strip().lower()
        if not normalized_model_name:
            raise PredictionValidationError("`model_name` must not be empty.")
        if not normalized_artifact_kind:
            raise PredictionValidationError("`artifact_kind` must not be empty.")
        if not normalized_artifact_path:
            raise PredictionValidationError("`artifact_path` must not be empty.")
        if not normalized_artifact_sha:
            raise PredictionValidationError("`artifact_sha256` must not be empty.")
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if normalized_target_mode not in {"price", "return"}:
            raise PredictionValidationError("`target_mode` must be either 'price' or 'return'.")
        if self.reference_value == 0:
            raise PredictionValidationError("`reference_value` must not be zero.")

        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "model_name", normalized_model_name)
        object.__setattr__(self, "artifact_kind", normalized_artifact_kind)
        object.__setattr__(self, "artifact_path", normalized_artifact_path)
        object.__setattr__(self, "artifact_sha256", normalized_artifact_sha)
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))
        object.__setattr__(self, "prediction_time", ensure_utc(self.prediction_time))
        object.__setattr__(self, "target_field", normalized_target_field)
        object.__setattr__(self, "target_mode", normalized_target_mode)
        object.__setattr__(self, "predicted_direction", prediction_direction(self.predicted_return))
        object.__setattr__(self, "feature_names", tuple(self.feature_names))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if self.created_at is not None:
            object.__setattr__(self, "created_at", ensure_utc(self.created_at))
        if self.updated_at is not None:
            object.__setattr__(self, "updated_at", ensure_utc(self.updated_at))
        if self.settled_at is not None:
            object.__setattr__(self, "settled_at", ensure_utc(self.settled_at))


@dataclass(frozen=True, slots=True)
class PredictionJournalSettlement:
    """Computed settlement payload for one prediction journal entry."""

    journal_id: int
    actual_value: float
    actual_return: float
    actual_direction: str
    absolute_error: float
    absolute_percentage_error: float
    direction_correct: bool
    settled_at: datetime


@dataclass(frozen=True, slots=True)
class PredictionJournalSummary:
    """Aggregate prediction journal metrics for one query window."""

    symbol: str
    interval: str
    model_name: str | None
    start_time: datetime
    end_time: datetime
    prediction_count: int
    settled_count: int
    mape: float | None
    rmse: float | None
    direction_accuracy: float | None
    mean_predicted_return: float | None
    mean_actual_return: float | None
    predicted_direction_counts: dict[str, int]
    actual_direction_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable summary."""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "model_name": self.model_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "prediction_count": self.prediction_count,
            "settled_count": self.settled_count,
            "mape": self.mape,
            "rmse": self.rmse,
            "direction_accuracy": self.direction_accuracy,
            "mean_predicted_return": self.mean_predicted_return,
            "mean_actual_return": self.mean_actual_return,
            "predicted_direction_counts": self.predicted_direction_counts,
            "actual_direction_counts": self.actual_direction_counts,
        }
