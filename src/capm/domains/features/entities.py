"""Domain entities and helpers for computed features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from capm.domains.market_data import OHLCV, interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc

from .errors import FeatureValidationError, IndicatorConfigurationError

IndicatorValue = Decimal | None
SUPPORTED_INDICATOR_KINDS = frozenset({"sma", "ema", "rsi", "macd", "bbands"})
SUPPORTED_SOURCE_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    }
)


def _as_positive_int(parameters: dict[str, Any], key: str) -> int:
    value = parameters.get(key)
    if not isinstance(value, int) or value < 1:
        raise IndicatorConfigurationError(f"`{key}` must be a positive integer.")
    return value


def _as_positive_decimal(parameters: dict[str, Any], key: str) -> Decimal:
    value = parameters.get(key)
    try:
        decimal_value = Decimal(str(value))
    except Exception as exc:  # pragma: no cover - Decimal errors vary by input type.
        raise IndicatorConfigurationError(f"`{key}` must be numeric.") from exc
    if decimal_value <= 0:
        raise IndicatorConfigurationError(f"`{key}` must be positive.")
    return decimal_value


def build_feature_name(kind: str, source_field: str, parameters: dict[str, Any], suffix: str | None = None) -> str:
    """Create a stable feature name for one indicator output."""
    normalized_kind = kind.strip().lower()
    if normalized_kind == "macd":
        base = (
            f"macd_{parameters['fast_period']}_{parameters['slow_period']}"
            f"_{parameters['signal_period']}"
        )
    elif normalized_kind == "bbands":
        multiplier = str(parameters["stddev_multiplier"]).replace(".", "_")
        base = f"bbands_{parameters['period']}_{multiplier}"
    else:
        base = f"{normalized_kind}_{parameters['period']}_{source_field}"

    if normalized_kind in {"macd", "bbands"} and suffix is None:
        return f"{base}_{source_field}"
    if suffix is None:
        return base
    return f"{base}_{suffix}"


@dataclass(frozen=True, slots=True)
class IndicatorSpec:
    """Configuration for one built-in technical indicator."""

    name: str
    kind: str
    parameters: dict[str, Any]
    enabled: bool = True
    source_field: str = "close"
    output_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_kind = self.kind.strip().lower()
        if normalized_kind not in SUPPORTED_INDICATOR_KINDS:
            raise IndicatorConfigurationError(
                f"Unsupported indicator kind {self.kind!r}. "
                f"Expected one of {sorted(SUPPORTED_INDICATOR_KINDS)}."
            )

        normalized_source_field = self.source_field.strip().lower()
        if normalized_source_field not in SUPPORTED_SOURCE_FIELDS:
            raise IndicatorConfigurationError(
                f"Unsupported indicator source field {self.source_field!r}. "
                f"Expected one of {sorted(SUPPORTED_SOURCE_FIELDS)}."
            )

        normalized_parameters = dict(self.parameters)
        if normalized_kind in {"sma", "ema", "rsi"}:
            normalized_parameters["period"] = _as_positive_int(normalized_parameters, "period")
            output_names = (build_feature_name(normalized_kind, normalized_source_field, normalized_parameters),)
        elif normalized_kind == "macd":
            normalized_parameters["fast_period"] = _as_positive_int(normalized_parameters, "fast_period")
            normalized_parameters["slow_period"] = _as_positive_int(normalized_parameters, "slow_period")
            normalized_parameters["signal_period"] = _as_positive_int(normalized_parameters, "signal_period")
            if normalized_parameters["fast_period"] >= normalized_parameters["slow_period"]:
                raise IndicatorConfigurationError("`fast_period` must be smaller than `slow_period`.")
            output_names = (
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "line"),
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "signal"),
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "histogram"),
            )
        else:
            normalized_parameters["period"] = _as_positive_int(normalized_parameters, "period")
            normalized_parameters["stddev_multiplier"] = _as_positive_decimal(
                normalized_parameters,
                "stddev_multiplier",
            )
            output_names = (
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "middle"),
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "upper"),
                build_feature_name(normalized_kind, normalized_source_field, normalized_parameters, "lower"),
            )

        normalized_name = self.name.strip() or output_names[0]

        object.__setattr__(self, "kind", normalized_kind)
        object.__setattr__(self, "source_field", normalized_source_field)
        object.__setattr__(self, "parameters", normalized_parameters)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "output_names", output_names if not self.output_names else tuple(self.output_names))

    @property
    def required_lookback(self) -> int:
        """Return the minimum number of candles required for a ready output."""
        if self.kind in {"sma", "ema", "bbands"}:
            return int(self.parameters["period"])
        if self.kind == "rsi":
            return int(self.parameters["period"]) + 1
        return int(self.parameters["slow_period"]) + int(self.parameters["signal_period"]) - 1


@dataclass(frozen=True, slots=True)
class ComputedIndicatorSet:
    """Computed indicator values for one candle-aligned timestamp."""

    symbol: str
    interval: str
    open_time: datetime
    values: dict[str, IndicatorValue]
    is_ready: bool
    missing_outputs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "open_time", ensure_utc(self.open_time))
        interval_to_timedelta(self.interval)
        object.__setattr__(self, "missing_outputs", tuple(sorted(self.missing_outputs)))


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """Canonical row that joins a candle with its indicator outputs."""

    candle: OHLCV
    indicator_values: dict[str, IndicatorValue]
    is_feature_ready: bool

    @property
    def symbol(self) -> str:
        """Return the symbol from the underlying candle."""
        return self.candle.symbol

    @property
    def interval(self) -> str:
        """Return the interval from the underlying candle."""
        return self.candle.interval

    @property
    def open_time(self) -> datetime:
        """Return the candle open time."""
        return self.candle.open_time

    @property
    def close_time(self) -> datetime:
        """Return the candle close time."""
        return self.candle.close_time

    @classmethod
    def from_components(cls, candle: OHLCV, indicators: ComputedIndicatorSet) -> FeatureRow:
        """Build a feature row from aligned raw and derived values."""
        if candle.symbol != indicators.symbol:
            raise FeatureValidationError("Feature row symbol mismatch.")
        if candle.interval != indicators.interval:
            raise FeatureValidationError("Feature row interval mismatch.")
        if candle.open_time != indicators.open_time:
            raise FeatureValidationError("Feature row timestamp mismatch.")
        return cls(
            candle=candle,
            indicator_values=dict(indicators.values),
            is_feature_ready=indicators.is_ready,
        )


@dataclass(frozen=True, slots=True)
class FeatureWindow:
    """Latest feature rows for one symbol and interval."""

    symbol: str
    interval: str
    rows: tuple[FeatureRow, ...]
    requested_features: tuple[str, ...]
    is_complete: bool
    gap_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "requested_features", tuple(sorted(set(self.requested_features))))
        interval_to_timedelta(self.interval)

        for row in self.rows:
            if row.symbol != self.symbol:
                raise FeatureValidationError("Feature window rows must use one symbol.")
            if row.interval != self.interval:
                raise FeatureValidationError("Feature window rows must use one interval.")

    @property
    def window_size(self) -> int:
        """Return the number of rows included in the window."""
        return len(self.rows)
