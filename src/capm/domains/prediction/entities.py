"""Domain entities shared across forecasting and backtesting flows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from capm.domains.features import FeatureRow
from capm.domains.market_data import OHLCV, interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc

from .errors import PredictionValidationError

ForecastRow = OHLCV | FeatureRow


def _validate_numeric_sequence(values: tuple[float, ...], *, field_name: str) -> None:
    if not values:
        raise PredictionValidationError(f"`{field_name}` must not be empty.")
    for value in values:
        if not isinstance(value, (int, float)):
            raise PredictionValidationError(f"`{field_name}` must contain only numeric values.")


@dataclass(frozen=True, slots=True)
class ForecastRequest:
    """Validated request for one forecasting experiment."""

    symbol: str
    interval: str
    target_field: str = "close"
    window_size: int = 100
    forecast_horizon: int = 1
    start_time: datetime | None = None
    end_time: datetime | None = None
    model_name: str = "arima"
    model_parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        normalized_symbol = normalize_symbol(self.symbol)
        interval_to_timedelta(self.interval)
        normalized_target_field = self.target_field.strip().lower()
        normalized_model_name = self.model_name.strip().lower()
        normalized_parameters = dict(self.model_parameters or {})

        normalized_start_time = ensure_utc(self.start_time) if self.start_time else None
        normalized_end_time = ensure_utc(self.end_time) if self.end_time else None
        if normalized_start_time and normalized_end_time and normalized_start_time >= normalized_end_time:
            raise PredictionValidationError("`start_time` must be earlier than `end_time`.")
        if self.window_size < 1:
            raise PredictionValidationError("`window_size` must be positive.")
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if not normalized_target_field:
            raise PredictionValidationError("`target_field` must not be empty.")
        if not normalized_model_name:
            raise PredictionValidationError("`model_name` must not be empty.")

        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "target_field", normalized_target_field)
        object.__setattr__(self, "model_name", normalized_model_name)
        object.__setattr__(self, "model_parameters", normalized_parameters)
        object.__setattr__(self, "start_time", normalized_start_time)
        object.__setattr__(self, "end_time", normalized_end_time)


@dataclass(frozen=True, slots=True)
class ForecastDataset:
    """Canonical DB-backed dataset for one forecasting experiment."""

    symbol: str
    interval: str
    rows: tuple[ForecastRow, ...]
    target_field: str
    feature_names: tuple[str, ...]
    window_size: int
    forecast_horizon: int

    def __post_init__(self) -> None:
        normalized_symbol = normalize_symbol(self.symbol)
        interval_to_timedelta(self.interval)
        normalized_target_field = self.target_field.strip().lower()
        normalized_feature_names = tuple(dict.fromkeys(name.strip() for name in self.feature_names if name.strip()))

        if self.window_size < 1:
            raise PredictionValidationError("`window_size` must be positive.")
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if not self.rows:
            raise PredictionValidationError("`rows` must not be empty.")
        if len(self.rows) < self.window_size + self.forecast_horizon + 1:
            raise PredictionValidationError(
                "The dataset does not contain enough history for the requested window and horizon."
            )

        previous_open_time: datetime | None = None
        for row in self.rows:
            row_open_time = row.open_time
            if row.symbol != normalized_symbol:
                raise PredictionValidationError("Dataset rows must all use the requested symbol.")
            if row.interval != self.interval:
                raise PredictionValidationError("Dataset rows must all use the requested interval.")
            if previous_open_time is not None and row_open_time <= previous_open_time:
                raise PredictionValidationError("Dataset rows must be strictly ordered by timestamp.")
            previous_open_time = row_open_time

        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "target_field", normalized_target_field)
        object.__setattr__(self, "feature_names", normalized_feature_names)
        object.__setattr__(self, "rows", tuple(self.rows))

    @property
    def row_count(self) -> int:
        """Return the number of loaded canonical rows."""
        return len(self.rows)


@dataclass(frozen=True, slots=True)
class StatisticalTrainingInput:
    """Normalized univariate training slice for statistical models."""

    timestamps: tuple[datetime, ...]
    target_values: tuple[float, ...]
    interval: str

    def __post_init__(self) -> None:
        interval_to_timedelta(self.interval)
        if len(self.timestamps) != len(self.target_values):
            raise PredictionValidationError("Statistical inputs must align timestamps and targets.")
        if len(self.timestamps) < 2:
            raise PredictionValidationError("Statistical training requires at least two rows.")
        _validate_numeric_sequence(self.target_values, field_name="target_values")
        object.__setattr__(self, "timestamps", tuple(ensure_utc(timestamp) for timestamp in self.timestamps))


@dataclass(frozen=True, slots=True)
class StatisticalPredictionInput:
    """Prediction metadata for one horizon-based statistical forecast."""

    reference_time: datetime
    prediction_time: datetime
    reference_value: float
    forecast_horizon: int
    interval: str

    def __post_init__(self) -> None:
        interval_to_timedelta(self.interval)
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if self.prediction_time <= self.reference_time:
            raise PredictionValidationError("`prediction_time` must be later than `reference_time`.")
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))
        object.__setattr__(self, "prediction_time", ensure_utc(self.prediction_time))


@dataclass(frozen=True, slots=True)
class TabularTrainingInput:
    """Normalized tabular training slice for ML models."""

    timestamps: tuple[datetime, ...]
    feature_names: tuple[str, ...]
    feature_matrix: tuple[tuple[float, ...], ...]
    target_values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.timestamps) != len(self.feature_matrix) or len(self.timestamps) != len(self.target_values):
            raise PredictionValidationError("Tabular inputs must align timestamps, features, and targets.")
        if len(self.feature_matrix) < 2:
            raise PredictionValidationError("Tabular training requires at least two rows.")
        if not self.feature_names:
            raise PredictionValidationError("`feature_names` must not be empty.")
        _validate_numeric_sequence(self.target_values, field_name="target_values")
        expected_width = len(self.feature_names)
        for row in self.feature_matrix:
            if len(row) != expected_width:
                raise PredictionValidationError("Each feature row must match the declared feature names.")
            _validate_numeric_sequence(row, field_name="feature_matrix row")
        object.__setattr__(self, "timestamps", tuple(ensure_utc(timestamp) for timestamp in self.timestamps))


@dataclass(frozen=True, slots=True)
class TabularPredictionInput:
    """Prediction metadata and features for one tabular forecast."""

    reference_time: datetime
    prediction_time: datetime
    reference_value: float
    feature_names: tuple[str, ...]
    feature_vector: tuple[float, ...]
    forecast_horizon: int

    def __post_init__(self) -> None:
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if self.prediction_time <= self.reference_time:
            raise PredictionValidationError("`prediction_time` must be later than `reference_time`.")
        if not self.feature_names:
            raise PredictionValidationError("`feature_names` must not be empty.")
        if len(self.feature_names) != len(self.feature_vector):
            raise PredictionValidationError("`feature_vector` must align with `feature_names`.")
        _validate_numeric_sequence(self.feature_vector, field_name="feature_vector")
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))
        object.__setattr__(self, "prediction_time", ensure_utc(self.prediction_time))


@dataclass(frozen=True, slots=True)
class SequenceTrainingInput:
    """Normalized sequence training slice for deep-learning models."""

    timestamps: tuple[datetime, ...]
    feature_names: tuple[str, ...]
    sequences: tuple[tuple[tuple[float, ...], ...], ...]
    target_values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.timestamps) != len(self.sequences) or len(self.timestamps) != len(self.target_values):
            raise PredictionValidationError("Sequence inputs must align timestamps, sequences, and targets.")
        if len(self.sequences) < 1:
            raise PredictionValidationError("Sequence training requires at least one sample.")
        if not self.feature_names:
            raise PredictionValidationError("`feature_names` must not be empty.")
        _validate_numeric_sequence(self.target_values, field_name="target_values")
        expected_width = len(self.feature_names)
        expected_length = len(self.sequences[0])
        if expected_length < 1:
            raise PredictionValidationError("Each sequence must contain at least one step.")
        for sequence in self.sequences:
            if len(sequence) != expected_length:
                raise PredictionValidationError("All sequences must use the same sequence length.")
            for step in sequence:
                if len(step) != expected_width:
                    raise PredictionValidationError("Each sequence step must match the declared feature names.")
                _validate_numeric_sequence(step, field_name="sequence step")
        object.__setattr__(self, "timestamps", tuple(ensure_utc(timestamp) for timestamp in self.timestamps))


@dataclass(frozen=True, slots=True)
class SequencePredictionInput:
    """Prediction metadata and feature sequence for one deep-learning forecast."""

    reference_time: datetime
    prediction_time: datetime
    reference_value: float
    feature_names: tuple[str, ...]
    sequence: tuple[tuple[float, ...], ...]
    forecast_horizon: int

    def __post_init__(self) -> None:
        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if self.prediction_time <= self.reference_time:
            raise PredictionValidationError("`prediction_time` must be later than `reference_time`.")
        if not self.feature_names:
            raise PredictionValidationError("`feature_names` must not be empty.")
        if not self.sequence:
            raise PredictionValidationError("`sequence` must not be empty.")
        expected_width = len(self.feature_names)
        for step in self.sequence:
            if len(step) != expected_width:
                raise PredictionValidationError("Each sequence step must align with `feature_names`.")
            _validate_numeric_sequence(step, field_name="sequence step")
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))
        object.__setattr__(self, "prediction_time", ensure_utc(self.prediction_time))


@dataclass(frozen=True, slots=True)
class PreparedPredictionStep:
    """Prepared training and prediction payloads for one walk-forward step."""

    reference_index: int
    reference_time: datetime
    prediction_time: datetime
    reference_value: float
    actual_value: float
    training_input: StatisticalTrainingInput | TabularTrainingInput | SequenceTrainingInput
    prediction_input: StatisticalPredictionInput | TabularPredictionInput | SequencePredictionInput

    def __post_init__(self) -> None:
        if self.reference_index < 0:
            raise PredictionValidationError("`reference_index` must not be negative.")
        if self.prediction_time <= self.reference_time:
            raise PredictionValidationError("`prediction_time` must be later than `reference_time`.")
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))
        object.__setattr__(self, "prediction_time", ensure_utc(self.prediction_time))


@dataclass(frozen=True, slots=True)
class ForecastResult:
    """Model output batch over one validation slice."""

    symbol: str
    interval: str
    model_name: str
    prediction_times: tuple[datetime, ...]
    predicted_values: tuple[float, ...]
    actual_values: tuple[float, ...]
    forecast_horizon: int
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        normalized_symbol = normalize_symbol(self.symbol)
        interval_to_timedelta(self.interval)
        normalized_model_name = self.model_name.strip().lower()
        normalized_prediction_times = tuple(ensure_utc(timestamp) for timestamp in self.prediction_times)

        if self.forecast_horizon < 1:
            raise PredictionValidationError("`forecast_horizon` must be positive.")
        if not normalized_prediction_times:
            raise PredictionValidationError("`prediction_times` must not be empty.")
        if len(normalized_prediction_times) != len(self.predicted_values):
            raise PredictionValidationError("Prediction timestamps and values must align.")
        if len(self.actual_values) != len(self.predicted_values):
            raise PredictionValidationError("Actual values and predicted values must align.")
        _validate_numeric_sequence(tuple(float(value) for value in self.predicted_values), field_name="predicted_values")
        _validate_numeric_sequence(tuple(float(value) for value in self.actual_values), field_name="actual_values")

        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "model_name", normalized_model_name)
        object.__setattr__(self, "prediction_times", normalized_prediction_times)
        object.__setattr__(self, "predicted_values", tuple(float(value) for value in self.predicted_values))
        object.__setattr__(self, "actual_values", tuple(float(value) for value in self.actual_values))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Metric output for one experiment split or aggregate summary."""

    symbol: str
    interval: str
    model_name: str
    split_id: str
    rmse: float
    mape: float
    direction_accuracy: float
    fit_duration_seconds: float
    predict_duration_seconds: float
    artifact_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        interval_to_timedelta(self.interval)
        if not self.split_id.strip():
            raise PredictionValidationError("`split_id` must not be empty.")
        object.__setattr__(self, "model_name", self.model_name.strip().lower())
        object.__setattr__(self, "artifact_paths", tuple(self.artifact_paths))


@dataclass(frozen=True, slots=True)
class ExperimentRunSummary:
    """Aggregate output for one full walk-forward experiment."""

    run_id: str
    request: ForecastRequest
    split_results: tuple[ForecastResult, ...]
    evaluation_reports: tuple[EvaluationReport, ...]
    aggregate_report: EvaluationReport

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise PredictionValidationError("`run_id` must not be empty.")
        if not self.evaluation_reports:
            raise PredictionValidationError("An experiment summary requires at least one evaluation report.")


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Strategy-level outcome for one forecast-driven simulation."""

    symbol: str
    interval: str
    model_name: str
    trade_count: int
    profit_factor: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    cumulative_return: float
    buy_and_hold_return: float
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        interval_to_timedelta(self.interval)
        if self.trade_count < 0:
            raise PredictionValidationError("`trade_count` must not be negative.")
        object.__setattr__(self, "model_name", self.model_name.strip().lower())
        object.__setattr__(self, "notes", tuple(self.notes))
