"""Domain entities and helpers for forecasting experiments."""

from .entities import (
    BacktestReport,
    EvaluationReport,
    ExperimentRunSummary,
    ForecastDataset,
    ForecastRequest,
    ForecastResult,
    PreparedPredictionStep,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
    TabularPredictionInput,
    TabularTrainingInput,
)
from .errors import (
    BacktestConfigurationError,
    DatasetAdaptationError,
    ExperimentConfigurationError,
    MissingOptionalDependencyError,
    PredictionValidationError,
    SplitValidationError,
)
from .metrics import aggregate_reports, direction_accuracy, mape, rmse
from .signals import SignalAction, SignalDecision, ThresholdSignalPolicy, generate_threshold_signals
from .splits import WalkForwardSplit, build_walk_forward_splits

__all__ = [
    "BacktestConfigurationError",
    "BacktestReport",
    "DatasetAdaptationError",
    "EvaluationReport",
    "ExperimentConfigurationError",
    "ExperimentRunSummary",
    "ForecastDataset",
    "ForecastRequest",
    "ForecastResult",
    "MissingOptionalDependencyError",
    "PredictionValidationError",
    "PreparedPredictionStep",
    "SignalAction",
    "SignalDecision",
    "SplitValidationError",
    "StatisticalPredictionInput",
    "StatisticalTrainingInput",
    "TabularPredictionInput",
    "TabularTrainingInput",
    "ThresholdSignalPolicy",
    "WalkForwardSplit",
    "aggregate_reports",
    "build_walk_forward_splits",
    "direction_accuracy",
    "generate_threshold_signals",
    "mape",
    "rmse",
]
