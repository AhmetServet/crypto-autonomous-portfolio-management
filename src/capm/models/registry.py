"""Registry for supported forecasting model wrappers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from capm.core.contracts import ForecastModelPort

from .ml import LightGBMForecastingModel, XGBoostForecastingModel
from .statistical import ARIMAForecastingModel, ProphetForecastingModel


@dataclass(frozen=True, slots=True)
class RegisteredModel:
    """Model metadata plus a zero-state factory."""

    family: str
    factory: Callable[[dict[str, Any]], ForecastModelPort]


def _build_arima(parameters: dict[str, Any]) -> ForecastModelPort:
    order = tuple(parameters.get("order", (1, 0, 0)))
    if len(order) != 3:
        raise ValueError("ARIMA `order` must contain exactly three integers.")
    fit_kwargs = dict(parameters.get("fit_kwargs", {}))
    trend = parameters.get("trend")
    return ARIMAForecastingModel(
        order=(int(order[0]), int(order[1]), int(order[2])),
        trend=trend,
        fit_kwargs=fit_kwargs,
    )


def _build_prophet(parameters: dict[str, Any]) -> ForecastModelPort:
    return ProphetForecastingModel(model_kwargs=dict(parameters))


def _build_xgboost(parameters: dict[str, Any]) -> ForecastModelPort:
    return XGBoostForecastingModel(model_kwargs=dict(parameters))


def _build_lightgbm(parameters: dict[str, Any]) -> ForecastModelPort:
    return LightGBMForecastingModel(model_kwargs=dict(parameters))


MODEL_REGISTRY: dict[str, RegisteredModel] = {
    "arima": RegisteredModel(family="statistical", factory=_build_arima),
    "prophet": RegisteredModel(family="statistical", factory=_build_prophet),
    "xgboost": RegisteredModel(family="ml", factory=_build_xgboost),
    "lightgbm": RegisteredModel(family="ml", factory=_build_lightgbm),
}


def get_model_family(model_name: str) -> str:
    """Return the model family for one registered model."""
    return MODEL_REGISTRY[model_name.strip().lower()].family


def create_model(model_name: str, parameters: dict[str, Any] | None = None) -> ForecastModelPort:
    """Instantiate one registered forecasting model wrapper."""
    normalized_model_name = model_name.strip().lower()
    registration = MODEL_REGISTRY[normalized_model_name]
    return registration.factory(dict(parameters or {}))
