"""Thin Prophet forecasting wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency.
    pd = None

try:
    from prophet import Prophet
except ImportError:  # pragma: no cover - optional dependency.
    Prophet = None

from capm.domains.prediction import (
    DatasetAdaptationError,
    MissingOptionalDependencyError,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
)


def _to_prophet_timestamp(timestamp: Any) -> Any:
    """Return a timezone-naive UTC timestamp for Prophet's `ds` column."""
    if pd is None:
        return timestamp
    return pd.Timestamp(timestamp).tz_convert("UTC").tz_localize(None)


@dataclass(slots=True)
class ProphetForecastingModel:
    """Fits and predicts with Facebook Prophet."""

    model_kwargs: dict[str, Any] = field(default_factory=dict)
    _model: Any | None = field(init=False, default=None, repr=False)

    name: str = "prophet"
    family: str = "statistical"

    def fit(self, training_input: StatisticalTrainingInput) -> dict[str, Any]:
        """Fit Prophet on the provided `ds` / `y` series."""
        if pd is None or Prophet is None:
            raise MissingOptionalDependencyError(
                "Prophet support requires the optional `ml` dependencies (`pandas` and `prophet`)."
            )
        if not isinstance(training_input, StatisticalTrainingInput):
            raise DatasetAdaptationError("Prophet expects a statistical training input.")

        frame = pd.DataFrame(
            {
                "ds": [_to_prophet_timestamp(timestamp) for timestamp in training_input.timestamps],
                "y": list(training_input.target_values),
            }
        )
        self._model = Prophet(**self.model_kwargs)
        self._model.fit(frame)
        return {
            "training_rows": len(frame),
            "model_kwargs": dict(self.model_kwargs),
        }

    def predict(self, prediction_input: StatisticalPredictionInput) -> tuple[float, dict[str, Any]]:
        """Predict the requested future timestamp with the fitted Prophet model."""
        if pd is None:
            raise MissingOptionalDependencyError("Prophet prediction requires the optional `pandas` dependency.")
        if self._model is None:
            raise DatasetAdaptationError("The Prophet model must be fit before prediction.")
        if not isinstance(prediction_input, StatisticalPredictionInput):
            raise DatasetAdaptationError("Prophet expects a statistical prediction input.")

        future = pd.DataFrame({"ds": [_to_prophet_timestamp(prediction_input.prediction_time)]})
        forecast = self._model.predict(future)
        predicted_value = float(forecast["yhat"].iloc[-1])
        return predicted_value, {
            "prediction_time": prediction_input.prediction_time.isoformat(),
            "forecast_horizon": prediction_input.forecast_horizon,
        }
