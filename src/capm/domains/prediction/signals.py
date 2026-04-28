"""Deterministic forecast-to-signal mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .entities import ForecastResult
from .errors import PredictionValidationError

SignalAction = Literal["buy", "sell", "hold"]


@dataclass(frozen=True, slots=True)
class SignalDecision:
    """One deterministic trading decision derived from a forecast."""

    prediction_time: object
    action: SignalAction
    predicted_return: float


@dataclass(frozen=True, slots=True)
class ThresholdSignalPolicy:
    """V1 threshold-based forecast-to-signal policy."""

    buy_threshold: float = 0.0
    sell_threshold: float | None = None

    def __post_init__(self) -> None:
        resolved_sell_threshold = -self.buy_threshold if self.sell_threshold is None else self.sell_threshold
        if self.buy_threshold < 0:
            raise PredictionValidationError("`buy_threshold` must not be negative.")
        if resolved_sell_threshold > 0:
            raise PredictionValidationError("`sell_threshold` must not be positive.")
        object.__setattr__(self, "sell_threshold", resolved_sell_threshold)


def generate_threshold_signals(
    forecast_result: ForecastResult,
    *,
    policy: ThresholdSignalPolicy | None = None,
    reference_values: tuple[float, ...] | None = None,
) -> tuple[SignalDecision, ...]:
    """Convert forecast outputs into buy, sell, or hold actions."""
    resolved_policy = policy or ThresholdSignalPolicy()
    resolved_reference_values = reference_values
    if resolved_reference_values is None:
        raw_reference_values = forecast_result.metadata.get("reference_values")
        if not isinstance(raw_reference_values, list | tuple):
            raise PredictionValidationError("Forecast metadata must include `reference_values` for signal generation.")
        resolved_reference_values = tuple(float(value) for value in raw_reference_values)

    if len(resolved_reference_values) != len(forecast_result.predicted_values):
        raise PredictionValidationError("Reference values must align with prediction values.")

    decisions: list[SignalDecision] = []
    for prediction_time, reference_value, predicted_value in zip(
        forecast_result.prediction_times,
        resolved_reference_values,
        forecast_result.predicted_values,
        strict=True,
    ):
        if reference_value == 0:
            raise PredictionValidationError("Reference values must be non-zero for signal generation.")
        predicted_return = (predicted_value - reference_value) / reference_value
        if predicted_return > resolved_policy.buy_threshold:
            action: SignalAction = "buy"
        elif predicted_return < resolved_policy.sell_threshold:
            action = "sell"
        else:
            action = "hold"
        decisions.append(
            SignalDecision(
                prediction_time=prediction_time,
                action=action,
                predicted_return=predicted_return,
            )
        )
    return tuple(decisions)
