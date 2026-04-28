"""Thin XGBoost forecasting wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    from xgboost import XGBRegressor
except ImportError:  # pragma: no cover - optional dependency.
    XGBRegressor = None

from capm.domains.prediction import (
    DatasetAdaptationError,
    MissingOptionalDependencyError,
    TabularPredictionInput,
    TabularTrainingInput,
)


@dataclass(slots=True)
class XGBoostForecastingModel:
    """Fits and predicts with XGBoost's sklearn-style regressor."""

    model_kwargs: dict[str, Any] = field(default_factory=dict)
    _model: Any | None = field(init=False, default=None, repr=False)
    _feature_names: tuple[str, ...] = field(init=False, default=(), repr=False)

    name: str = "xgboost"
    family: str = "ml"

    def fit(self, training_input: TabularTrainingInput) -> dict[str, Any]:
        """Fit the XGBoost regressor on one tabular training slice."""
        if XGBRegressor is None:
            raise MissingOptionalDependencyError("XGBoost support requires the optional `ml` dependency `xgboost`.")
        if not isinstance(training_input, TabularTrainingInput):
            raise DatasetAdaptationError("XGBoost expects a tabular training input.")

        self._model = XGBRegressor(**self.model_kwargs)
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
        """Return one XGBoost forecast for the prepared feature vector."""
        if self._model is None:
            raise DatasetAdaptationError("The XGBoost model must be fit before prediction.")
        if not isinstance(prediction_input, TabularPredictionInput):
            raise DatasetAdaptationError("XGBoost expects a tabular prediction input.")

        predicted_value = float(self._model.predict([list(prediction_input.feature_vector)])[0])
        return predicted_value, {
            "prediction_time": prediction_input.prediction_time.isoformat(),
            "feature_names": list(prediction_input.feature_names),
        }
