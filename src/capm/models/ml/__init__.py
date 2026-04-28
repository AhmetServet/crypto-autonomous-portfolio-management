"""Tabular ML prediction model wrappers."""

from .lightgbm_model import LightGBMForecastingModel
from .xgboost_model import XGBoostForecastingModel

__all__ = ["LightGBMForecastingModel", "XGBoostForecastingModel"]
