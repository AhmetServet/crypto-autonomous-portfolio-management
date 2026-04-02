"""Pure technical indicator computations over OHLCV candles."""

from __future__ import annotations

from decimal import Decimal, localcontext

from capm.domains.market_data import OHLCV, interval_to_timedelta

from .entities import IndicatorSpec, IndicatorValue
from .errors import FeatureGapError, FeatureValidationError


def validate_candle_series(candles: list[OHLCV]) -> None:
    """Validate ordering, identity, and continuity for a candle series."""
    if not candles:
        return

    first = candles[0]
    interval_delta = interval_to_timedelta(first.interval)

    previous_open_time = first.open_time
    for index, candle in enumerate(candles):
        if candle.symbol != first.symbol:
            raise FeatureValidationError("All candles in a feature series must use one symbol.")
        if candle.interval != first.interval:
            raise FeatureValidationError("All candles in a feature series must use one interval.")
        if index == 0:
            continue
        if candle.open_time <= previous_open_time:
            raise FeatureValidationError("Candles must be strictly ordered by open_time.")
        if candle.open_time - previous_open_time != interval_delta:
            raise FeatureGapError("Candles must be continuous for deterministic feature computation.")
        previous_open_time = candle.open_time


def source_values(candles: list[OHLCV], source_field: str) -> list[Decimal]:
    """Extract one numeric candle field as a decimal series."""
    return [Decimal(str(getattr(candle, source_field))) for candle in candles]


def simple_moving_average(values: list[Decimal], period: int) -> list[IndicatorValue]:
    """Compute a simple moving average with `None` warm-up values."""
    results: list[IndicatorValue] = [None] * len(values)
    rolling_sum = Decimal("0")

    for index, value in enumerate(values):
        rolling_sum += value
        if index >= period:
            rolling_sum -= values[index - period]
        if index + 1 >= period:
            results[index] = rolling_sum / Decimal(period)

    return results


def exponential_moving_average(values: list[Decimal], period: int) -> list[IndicatorValue]:
    """Compute an EMA seeded by the first SMA window."""
    results: list[IndicatorValue] = [None] * len(values)
    if period > len(values):
        return results

    multiplier = Decimal("2") / Decimal(period + 1)
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    results[period - 1] = seed
    previous = seed

    for index in range(period, len(values)):
        previous = (values[index] - previous) * multiplier + previous
        results[index] = previous

    return results


def exponential_moving_average_optional(values: list[IndicatorValue], period: int) -> list[IndicatorValue]:
    """Compute an EMA over a sequence that may have leading `None` values."""
    results: list[IndicatorValue] = [None] * len(values)
    numeric_indices = [index for index, value in enumerate(values) if value is not None]
    if len(numeric_indices) < period:
        return results

    multiplier = Decimal("2") / Decimal(period + 1)
    seed_indices = numeric_indices[:period]
    seed_values = [values[index] for index in seed_indices]
    seed = sum((value for value in seed_values if value is not None), Decimal("0")) / Decimal(period)
    seed_index = seed_indices[-1]
    results[seed_index] = seed
    previous = seed

    for index in numeric_indices[period:]:
        value = values[index]
        if value is None:
            continue
        previous = (value - previous) * multiplier + previous
        results[index] = previous

    return results


def relative_strength_index(values: list[Decimal], period: int) -> list[IndicatorValue]:
    """Compute RSI using Wilder smoothing."""
    results: list[IndicatorValue] = [None] * len(values)
    if len(values) <= period:
        return results

    deltas = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(delta, Decimal("0")) for delta in deltas]
    losses = [max(-delta, Decimal("0")) for delta in deltas]

    average_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    average_loss = sum(losses[:period], Decimal("0")) / Decimal(period)
    results[period] = _rsi_from_averages(average_gain, average_loss)

    for index in range(period, len(deltas)):
        gain = gains[index]
        loss = losses[index]
        average_gain = ((average_gain * Decimal(period - 1)) + gain) / Decimal(period)
        average_loss = ((average_loss * Decimal(period - 1)) + loss) / Decimal(period)
        results[index + 1] = _rsi_from_averages(average_gain, average_loss)

    return results


def _rsi_from_averages(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    """Turn smoothed gains and losses into an RSI value."""
    if average_loss == 0 and average_gain == 0:
        return Decimal("50")
    if average_loss == 0:
        return Decimal("100")
    relative_strength = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))


def moving_average_convergence_divergence(
    values: list[Decimal],
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> list[dict[str, IndicatorValue]]:
    """Compute MACD line, signal line, and histogram."""
    fast_ema = exponential_moving_average(values, fast_period)
    slow_ema = exponential_moving_average(values, slow_period)

    line_values: list[IndicatorValue] = []
    for fast_value, slow_value in zip(fast_ema, slow_ema, strict=True):
        if fast_value is None or slow_value is None:
            line_values.append(None)
            continue
        line_values.append(fast_value - slow_value)

    signal_values = exponential_moving_average_optional(line_values, signal_period)

    results: list[dict[str, IndicatorValue]] = []
    for line_value, signal_value in zip(line_values, signal_values, strict=True):
        histogram = None
        if line_value is not None and signal_value is not None:
            histogram = line_value - signal_value
        results.append(
            {
                "line": line_value,
                "signal": signal_value,
                "histogram": histogram,
            }
        )

    return results


def bollinger_bands(
    values: list[Decimal],
    period: int,
    stddev_multiplier: Decimal,
) -> list[dict[str, IndicatorValue]]:
    """Compute Bollinger Bands with population standard deviation."""
    middle_values = simple_moving_average(values, period)
    results: list[dict[str, IndicatorValue]] = []

    for index, middle in enumerate(middle_values):
        if middle is None:
            results.append({"middle": None, "upper": None, "lower": None})
            continue

        window = values[index - period + 1 : index + 1]
        variance = sum(((value - middle) ** 2 for value in window), Decimal("0")) / Decimal(period)
        with localcontext() as context:
            context.prec = 28
            standard_deviation = variance.sqrt()
        offset = standard_deviation * stddev_multiplier
        results.append(
            {
                "middle": middle,
                "upper": middle + offset,
                "lower": middle - offset,
            }
        )

    return results


def compute_indicator_outputs(spec: IndicatorSpec, candles: list[OHLCV]) -> list[dict[str, IndicatorValue]]:
    """Compute one indicator specification over a validated candle series."""
    validate_candle_series(candles)
    values = source_values(candles, spec.source_field)

    if spec.kind == "sma":
        outputs = simple_moving_average(values, int(spec.parameters["period"]))
        return [{spec.output_names[0]: value} for value in outputs]

    if spec.kind == "ema":
        outputs = exponential_moving_average(values, int(spec.parameters["period"]))
        return [{spec.output_names[0]: value} for value in outputs]

    if spec.kind == "rsi":
        outputs = relative_strength_index(values, int(spec.parameters["period"]))
        return [{spec.output_names[0]: value} for value in outputs]

    if spec.kind == "macd":
        outputs = moving_average_convergence_divergence(
            values,
            fast_period=int(spec.parameters["fast_period"]),
            slow_period=int(spec.parameters["slow_period"]),
            signal_period=int(spec.parameters["signal_period"]),
        )
        return [
            {
                spec.output_names[0]: result["line"],
                spec.output_names[1]: result["signal"],
                spec.output_names[2]: result["histogram"],
            }
            for result in outputs
        ]

    if spec.kind == "bbands":
        outputs = bollinger_bands(
            values,
            period=int(spec.parameters["period"]),
            stddev_multiplier=Decimal(str(spec.parameters["stddev_multiplier"])),
        )
        return [
            {
                spec.output_names[0]: result["middle"],
                spec.output_names[1]: result["upper"],
                spec.output_names[2]: result["lower"],
            }
            for result in outputs
        ]

    raise FeatureValidationError(f"Unsupported indicator kind {spec.kind!r}.")
