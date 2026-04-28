"""Prediction-domain specific exceptions."""

from capm.core.errors import CAPMError, ConfigurationError, ValidationError


class PredictionValidationError(ValidationError):
    """Raised when a prediction-domain object is invalid."""


class SplitValidationError(PredictionValidationError):
    """Raised when walk-forward split boundaries are invalid."""


class DatasetAdaptationError(CAPMError):
    """Raised when canonical rows cannot be shaped for a model family."""


class MissingOptionalDependencyError(ConfigurationError):
    """Raised when an optional ML or backtesting dependency is unavailable."""


class ExperimentConfigurationError(ConfigurationError):
    """Raised when an experiment runner configuration is invalid."""


class BacktestConfigurationError(ConfigurationError):
    """Raised when backtest configuration is invalid."""
