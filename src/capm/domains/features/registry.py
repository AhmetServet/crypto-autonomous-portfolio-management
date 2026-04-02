"""Registry for configured built-in indicator specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from capm.domains.market_data import OHLCV

from .entities import ComputedIndicatorSet, IndicatorSpec
from .indicators import compute_indicator_outputs, validate_candle_series


def build_indicator_specs(configs: Iterable[Mapping[str, Any]]) -> tuple[IndicatorSpec, ...]:
    """Build validated indicator specs from config-like mappings."""
    return tuple(
        IndicatorSpec(
            name=str(config.get("name", "")),
            kind=str(config["kind"]),
            parameters=dict(config.get("parameters", {})),
            enabled=bool(config.get("enabled", True)),
            source_field=str(config.get("source_field", "close")),
        )
        for config in configs
    )


@dataclass(frozen=True, slots=True)
class IndicatorRegistry:
    """Resolve configured specs to concrete built-in computations."""

    specs: tuple[IndicatorSpec, ...]

    @classmethod
    def from_configs(cls, configs: Iterable[Mapping[str, Any]]) -> IndicatorRegistry:
        """Build the registry directly from config dictionaries."""
        return cls(specs=build_indicator_specs(configs))

    @property
    def enabled_specs(self) -> tuple[IndicatorSpec, ...]:
        """Return enabled indicator specs in declared order."""
        return tuple(spec for spec in self.specs if spec.enabled)

    @property
    def max_lookback(self) -> int:
        """Return the longest warm-up length across enabled indicators."""
        enabled = self.enabled_specs
        if not enabled:
            return 1
        return max(spec.required_lookback for spec in enabled)

    def compute(self, candles: list[OHLCV]) -> list[ComputedIndicatorSet]:
        """Compute all enabled indicators for a validated candle series."""
        validate_candle_series(candles)
        if not candles:
            return []

        enabled_specs = self.enabled_specs
        if not enabled_specs:
            return [
                ComputedIndicatorSet(
                    symbol=candle.symbol,
                    interval=candle.interval,
                    open_time=candle.open_time,
                    values={},
                    is_ready=True,
                    missing_outputs=(),
                )
                for candle in candles
            ]

        aggregated_values = [dict() for _ in candles]
        for spec in enabled_specs:
            outputs = compute_indicator_outputs(spec, candles)
            for index, output in enumerate(outputs):
                aggregated_values[index].update(output)

        computed: list[ComputedIndicatorSet] = []
        for candle, values in zip(candles, aggregated_values, strict=True):
            missing_outputs = tuple(sorted(name for name, value in values.items() if value is None))
            computed.append(
                ComputedIndicatorSet(
                    symbol=candle.symbol,
                    interval=candle.interval,
                    open_time=candle.open_time,
                    values=values,
                    is_ready=not missing_outputs,
                    missing_outputs=missing_outputs,
                )
            )

        return computed
