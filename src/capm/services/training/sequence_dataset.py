"""Sequence dataset shaping and scaling for deep-learning models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Any

from capm.domains.features import FeatureRow
from capm.domains.market_data import interval_to_timedelta
from capm.domains.prediction import PredictionValidationError, SequencePredictionInput, SequenceTrainingInput


@dataclass(frozen=True, slots=True)
class FeatureScaler:
    """Simple per-feature scaler fitted on training rows only."""

    mode: str
    feature_names: tuple[str, ...]
    centers: tuple[float, ...]
    scales: tuple[float, ...]

    @classmethod
    def fit(
        cls,
        values: tuple[tuple[float, ...], ...],
        *,
        feature_names: tuple[str, ...],
        mode: str = "zscore",
    ) -> "FeatureScaler":
        """Fit a scaler from flat training feature rows."""
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"zscore", "minmax", "none"}:
            raise PredictionValidationError("Scaler mode must be one of 'zscore', 'minmax', or 'none'.")
        if not values:
            raise PredictionValidationError("Cannot fit a feature scaler without values.")
        width = len(feature_names)
        if width < 1:
            raise PredictionValidationError("Feature scaler requires at least one feature.")
        for row in values:
            if len(row) != width:
                raise PredictionValidationError("Feature rows must match feature_names width.")

        columns = tuple(tuple(row[index] for row in values) for index in range(width))
        if normalized_mode == "none":
            centers = tuple(0.0 for _ in feature_names)
            scales = tuple(1.0 for _ in feature_names)
        elif normalized_mode == "minmax":
            centers = tuple(min(column) for column in columns)
            scales = tuple((max(column) - min(column)) or 1.0 for column in columns)
        else:
            centers = tuple(sum(column) / len(column) for column in columns)
            scales = []
            for column, center in zip(columns, centers, strict=True):
                variance = sum((value - center) ** 2 for value in column) / len(column)
                scales.append((variance**0.5) or 1.0)
            scales = tuple(scales)
        return cls(
            mode=normalized_mode,
            feature_names=feature_names,
            centers=tuple(float(value) for value in centers),
            scales=tuple(float(value) for value in scales),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "FeatureScaler":
        """Rebuild a scaler from an artifact payload."""
        return cls(
            mode=str(payload["mode"]),
            feature_names=tuple(str(name) for name in payload["feature_names"]),
            centers=tuple(float(value) for value in payload["centers"]),
            scales=tuple(float(value) for value in payload["scales"]),
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialize scaler metadata for model artifacts."""
        return {
            "mode": self.mode,
            "feature_names": list(self.feature_names),
            "centers": list(self.centers),
            "scales": list(self.scales),
        }

    def transform_row(self, row: tuple[float, ...]) -> tuple[float, ...]:
        """Scale one feature row."""
        if len(row) != len(self.feature_names):
            raise PredictionValidationError("Feature row width does not match scaler feature names.")
        return tuple(
            (float(value) - center) / scale
            for value, center, scale in zip(row, self.centers, self.scales, strict=True)
        )

    def transform_sequence(self, sequence: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
        """Scale a whole sequence."""
        return tuple(self.transform_row(row) for row in sequence)


@dataclass(frozen=True, slots=True)
class ArraySequenceDataset:
    """Compact array-backed sequence dataset for large recurrent-model runs."""

    feature_matrix: Any
    target_values: Any
    reference_indices: Any
    timestamps: tuple[datetime, ...]
    reference_values: Any
    actual_values: Any
    feature_names: tuple[str, ...]
    sequence_length: int


@dataclass(frozen=True, slots=True)
class SequenceDataset:
    """Aligned sequence dataset for deep-learning model training or evaluation."""

    timestamps: tuple[datetime, ...]
    reference_values: tuple[float, ...]
    actual_values: tuple[float, ...]
    sequences: tuple[tuple[tuple[float, ...], ...], ...]
    target_values: tuple[float, ...]
    feature_names: tuple[str, ...]

    def to_training_input(self) -> SequenceTrainingInput:
        """Return the model-facing training input."""
        return SequenceTrainingInput(
            timestamps=self.timestamps,
            feature_names=self.feature_names,
            sequences=self.sequences,
            target_values=self.target_values,
        )


def field_value(row: FeatureRow, target_field: str) -> float:
    """Read one numeric OHLCV field from a feature row."""
    return float(getattr(row.candle, target_field))


def target_value(row: FeatureRow, target_row: FeatureRow, target_field: str, target_mode: str) -> float:
    """Build an aligned price or return target."""
    reference_value = field_value(row, target_field)
    future_value = field_value(target_row, target_field)
    if target_mode == "price":
        return future_value
    if target_mode == "return":
        if reference_value == 0:
            raise PredictionValidationError("Cannot compute return target from a zero reference value.")
        return (future_value - reference_value) / reference_value
    raise PredictionValidationError("target_mode must be either 'price' or 'return'.")


def target_to_price(reference_value: float, predicted_target: float, target_mode: str) -> float:
    """Convert a model target prediction into a forecast price."""
    if target_mode == "price":
        return predicted_target
    if target_mode == "return":
        return reference_value * (1 + predicted_target)
    raise PredictionValidationError("target_mode must be either 'price' or 'return'.")


def infer_ready_feature_names(rows: tuple[FeatureRow, ...]) -> tuple[str, ...]:
    """Infer common non-null indicator feature names from ready rows."""
    ready_rows = tuple(row for row in rows if row.is_feature_ready)
    if not ready_rows:
        raise PredictionValidationError("Cannot infer feature names without ready feature rows.")
    names = set(ready_rows[0].indicator_values)
    for row in ready_rows[1:]:
        names &= {name for name, value in row.indicator_values.items() if value is not None}
    return tuple(sorted(names))


def extract_feature_vector(row: FeatureRow, feature_names: tuple[str, ...]) -> tuple[float, ...]:
    """Read and validate one feature vector from a FeatureRow."""
    if not row.is_feature_ready:
        raise PredictionValidationError(f"Feature row at {row.open_time.isoformat()} is not ready.")
    values: list[float] = []
    for name in feature_names:
        value = row.indicator_values.get(name)
        if value is None:
            raise PredictionValidationError(f"Feature row missing required feature {name!r}.")
        numeric = float(value)
        if not isfinite(numeric):
            raise PredictionValidationError(f"Feature {name!r} is not finite.")
        values.append(numeric)
    return tuple(values)


def rows_are_consecutive(rows: tuple[FeatureRow, ...]) -> bool:
    """Return whether rows are contiguous at their declared interval."""
    if len(rows) < 2:
        return True
    interval_delta = interval_to_timedelta(rows[0].interval)
    return all(current.open_time - previous.open_time == interval_delta for previous, current in zip(rows, rows[1:]))


def fit_feature_scaler_from_rows(
    rows: tuple[FeatureRow, ...],
    *,
    feature_names: tuple[str, ...],
    mode: str,
) -> FeatureScaler:
    """Fit a scaler from feature rows without materializing nested Python tuples."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency.
        raise PredictionValidationError("Large sequence training requires numpy.") from exc

    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"zscore", "minmax", "none"}:
        raise PredictionValidationError("Scaler mode must be one of 'zscore', 'minmax', or 'none'.")
    if not rows:
        raise PredictionValidationError("Cannot fit a feature scaler without rows.")
    matrix = np.empty((len(rows), len(feature_names)), dtype=np.float32)
    for row_index, row in enumerate(rows):
        matrix[row_index] = extract_feature_vector(row, feature_names)
    if normalized_mode == "none":
        centers = np.zeros(len(feature_names), dtype=np.float32)
        scales = np.ones(len(feature_names), dtype=np.float32)
    elif normalized_mode == "minmax":
        centers = matrix.min(axis=0)
        scales = matrix.max(axis=0) - centers
        scales[scales == 0.0] = 1.0
    else:
        centers = matrix.mean(axis=0)
        scales = matrix.std(axis=0)
        scales[scales == 0.0] = 1.0
    return FeatureScaler(
        mode=normalized_mode,
        feature_names=feature_names,
        centers=tuple(float(value) for value in centers),
        scales=tuple(float(value) for value in scales),
    )


def build_array_sequence_dataset(
    *,
    rows: tuple[FeatureRow, ...],
    feature_names: tuple[str, ...],
    sequence_length: int,
    forecast_horizon: int,
    target_field: str,
    target_mode: str,
    start_index: int,
    end_index: int,
    scaler: FeatureScaler,
) -> ArraySequenceDataset:
    """Build compact arrays and valid reference indices for large sequence runs."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency.
        raise PredictionValidationError("Large sequence training requires numpy.") from exc

    if sequence_length < 1:
        raise PredictionValidationError("sequence_length must be positive.")
    if forecast_horizon < 1:
        raise PredictionValidationError("forecast_horizon must be positive.")
    if not feature_names:
        raise PredictionValidationError("feature_names must not be empty.")
    if not rows:
        raise PredictionValidationError("Cannot build sequence arrays without rows.")

    feature_matrix = np.empty((len(rows), len(feature_names)), dtype=np.float32)
    raw_values = np.empty(len(rows), dtype=np.float32)
    consecutive_lengths = np.ones(len(rows), dtype=np.int32)
    interval_delta = interval_to_timedelta(rows[0].interval)
    for row_index, row in enumerate(rows):
        feature_matrix[row_index] = scaler.transform_row(extract_feature_vector(row, feature_names))
        raw_values[row_index] = field_value(row, target_field)
        if row_index > 0 and row.open_time - rows[row_index - 1].open_time == interval_delta:
            consecutive_lengths[row_index] = consecutive_lengths[row_index - 1] + 1

    reference_indices: list[int] = []
    timestamps: list[datetime] = []
    reference_values: list[float] = []
    actual_values: list[float] = []
    targets: list[float] = []
    first_reference_index = max(start_index, sequence_length - 1)
    for reference_index in range(first_reference_index, end_index):
        target_index = reference_index + forecast_horizon
        if target_index >= len(rows):
            break
        if consecutive_lengths[reference_index] < sequence_length:
            continue
        reference_value = float(raw_values[reference_index])
        actual_value = float(raw_values[target_index])
        if target_mode == "price":
            target = actual_value
        elif target_mode == "return":
            if reference_value == 0:
                raise PredictionValidationError("Cannot compute return target from a zero reference value.")
            target = (actual_value - reference_value) / reference_value
        else:
            raise PredictionValidationError("target_mode must be either 'price' or 'return'.")
        reference_indices.append(reference_index)
        timestamps.append(rows[reference_index].open_time)
        reference_values.append(reference_value)
        actual_values.append(actual_value)
        targets.append(target)
    if not reference_indices:
        raise PredictionValidationError("No valid sequence samples were built.")
    return ArraySequenceDataset(
        feature_matrix=feature_matrix,
        target_values=np.asarray(targets, dtype=np.float32),
        reference_indices=np.asarray(reference_indices, dtype=np.int64),
        timestamps=tuple(timestamps),
        reference_values=np.asarray(reference_values, dtype=np.float32),
        actual_values=np.asarray(actual_values, dtype=np.float32),
        feature_names=feature_names,
        sequence_length=sequence_length,
    )


def build_sequence_dataset(
    *,
    rows: tuple[FeatureRow, ...],
    feature_names: tuple[str, ...],
    sequence_length: int,
    forecast_horizon: int,
    target_field: str,
    target_mode: str,
    start_index: int,
    end_index: int,
    scaler: FeatureScaler | None = None,
) -> SequenceDataset:
    """Build aligned sequence samples for references in [start_index, end_index)."""
    if sequence_length < 1:
        raise PredictionValidationError("sequence_length must be positive.")
    if forecast_horizon < 1:
        raise PredictionValidationError("forecast_horizon must be positive.")
    if not feature_names:
        raise PredictionValidationError("feature_names must not be empty.")
    interval_delta = interval_to_timedelta(rows[0].interval) if rows else None
    timestamps: list[datetime] = []
    reference_values: list[float] = []
    actual_values: list[float] = []
    sequences: list[tuple[tuple[float, ...], ...]] = []
    targets: list[float] = []

    first_reference_index = max(start_index, sequence_length - 1)
    for reference_index in range(first_reference_index, end_index):
        target_index = reference_index + forecast_horizon
        if target_index >= len(rows):
            break
        window = rows[reference_index - sequence_length + 1 : reference_index + 1]
        if len(window) != sequence_length:
            continue
        if interval_delta is not None and not rows_are_consecutive(tuple(window)):
            continue
        sequence = tuple(extract_feature_vector(row, feature_names) for row in window)
        if scaler is not None:
            sequence = scaler.transform_sequence(sequence)
        row = rows[reference_index]
        target_row = rows[target_index]
        timestamps.append(row.open_time)
        reference_values.append(field_value(row, target_field))
        actual_values.append(field_value(target_row, target_field))
        sequences.append(sequence)
        targets.append(target_value(row, target_row, target_field, target_mode))

    if not sequences:
        raise PredictionValidationError("No valid sequence samples were built.")
    return SequenceDataset(
        timestamps=tuple(timestamps),
        reference_values=tuple(reference_values),
        actual_values=tuple(actual_values),
        sequences=tuple(sequences),
        target_values=tuple(targets),
        feature_names=feature_names,
    )


def build_sequence_prediction_input(
    *,
    rows: tuple[FeatureRow, ...],
    feature_names: tuple[str, ...],
    forecast_horizon: int,
    target_field: str,
    scaler: FeatureScaler | None = None,
) -> SequencePredictionInput:
    """Build a model-facing prediction input from one complete feature window."""
    if not rows:
        raise PredictionValidationError("Prediction window must not be empty.")
    if not rows_are_consecutive(rows):
        raise PredictionValidationError("Prediction window rows must be consecutive.")
    sequence = tuple(extract_feature_vector(row, feature_names) for row in rows)
    if scaler is not None:
        sequence = scaler.transform_sequence(sequence)
    reference = rows[-1]
    prediction_time = reference.open_time + (interval_to_timedelta(reference.interval) * forecast_horizon)
    return SequencePredictionInput(
        reference_time=reference.open_time,
        prediction_time=prediction_time,
        reference_value=field_value(reference, target_field),
        feature_names=feature_names,
        sequence=sequence,
        forecast_horizon=forecast_horizon,
    )
