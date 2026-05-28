"""Thin LightGBM forecasting wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from lightgbm import LGBMRegressor
except ImportError:  # pragma: no cover - optional dependency.
    LGBMRegressor = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency.
    pd = None

from capm.domains.prediction import (
    DatasetAdaptationError,
    MissingOptionalDependencyError,
    TabularPredictionInput,
    TabularTrainingInput,
)


@dataclass(slots=True)
class LightGBMForecastingModel:
    """Fits and predicts with LightGBM's sklearn-style regressor."""

    model_kwargs: dict[str, Any] = field(default_factory=dict)
    _model: Any | None = field(init=False, default=None, repr=False)
    _feature_names: tuple[str, ...] = field(init=False, default=(), repr=False)

    name: str = "lightgbm"
    family: str = "ml"

    def fit(self, training_input: TabularTrainingInput) -> dict[str, Any]:
        """Fit the LightGBM regressor on one tabular training slice."""
        if LGBMRegressor is None:
            raise MissingOptionalDependencyError(
                "LightGBM support requires the optional `ml` dependency `lightgbm`."
            )
        if not isinstance(training_input, TabularTrainingInput):
            raise DatasetAdaptationError("LightGBM expects a tabular training input.")

        self._model = LGBMRegressor(**self.model_kwargs)
        self._model.fit(training_input.feature_matrix, training_input.target_values)
        self._feature_names = training_input.feature_names

        feature_importances = getattr(self._model, "feature_importances_", None)
        return {
            "feature_importances": (
                {
                    feature_name: float(importance)
                    for feature_name, importance in zip(self._feature_names, feature_importances, strict=True)
                }
                if feature_importances is not None
                else {}
            ),
            "model_kwargs": dict(self.model_kwargs),
        }

    def predict(self, prediction_input: TabularPredictionInput) -> tuple[float, dict[str, Any]]:
        """Return one LightGBM forecast for the prepared feature vector."""
        if self._model is None:
            raise DatasetAdaptationError("The LightGBM model must be fit before prediction.")
        if not isinstance(prediction_input, TabularPredictionInput):
            raise DatasetAdaptationError("LightGBM expects a tabular prediction input.")

        if pd is not None:
            prediction_frame = pd.DataFrame(
                [list(prediction_input.feature_vector)],
                columns=list(prediction_input.feature_names),
            )
            predicted_value = float(self._model.predict(prediction_frame)[0])
        else:
            predicted_value = float(self._model.predict([list(prediction_input.feature_vector)])[0])
        return predicted_value, {
            "prediction_time": prediction_input.prediction_time.isoformat(),
            "feature_names": list(prediction_input.feature_names),
        }
