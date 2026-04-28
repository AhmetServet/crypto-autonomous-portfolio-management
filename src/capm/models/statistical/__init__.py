"""Statistical prediction model wrappers."""

from .arima import ARIMAForecastingModel
from .prophet_model import ProphetForecastingModel

__all__ = ["ARIMAForecastingModel", "ProphetForecastingModel"]
