"""Domain entities and helpers for technical indicators and feature windows."""

from .entities import ComputedIndicatorSet, FeatureRow, FeatureWindow, IndicatorSpec
from .errors import (
    FeatureGapError,
    FeatureValidationError,
    IncompleteWindowError,
    IndicatorConfigurationError,
)
from .registry import IndicatorRegistry, build_indicator_specs
from .windowing import (
    GAP_REASON_INSUFFICIENT_HISTORY,
    GAP_REASON_MISSING_CANDLE_CONTINUITY,
    GAP_REASON_MISSING_DERIVED_ROWS,
    GAP_REASON_PARTIAL_WARMUP,
    build_feature_rows,
    build_feature_window,
)

__all__ = [
    "ComputedIndicatorSet",
    "FeatureGapError",
    "FeatureRow",
    "FeatureValidationError",
    "FeatureWindow",
    "GAP_REASON_INSUFFICIENT_HISTORY",
    "GAP_REASON_MISSING_CANDLE_CONTINUITY",
    "GAP_REASON_MISSING_DERIVED_ROWS",
    "GAP_REASON_PARTIAL_WARMUP",
    "IncompleteWindowError",
    "IndicatorConfigurationError",
    "IndicatorRegistry",
    "IndicatorSpec",
    "build_feature_rows",
    "build_feature_window",
    "build_indicator_specs",
]
