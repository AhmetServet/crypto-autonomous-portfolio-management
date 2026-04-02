"""Helpers for canonical feature rows and windows."""

from __future__ import annotations

from capm.domains.market_data import OHLCV, interval_to_timedelta, normalize_symbol

from .entities import ComputedIndicatorSet, FeatureRow, FeatureWindow
from .errors import FeatureGapError, FeatureValidationError, IncompleteWindowError

GAP_REASON_INSUFFICIENT_HISTORY = "insufficient_history"
GAP_REASON_MISSING_CANDLE_CONTINUITY = "missing_candle_continuity"
GAP_REASON_MISSING_DERIVED_ROWS = "missing_derived_feature_rows"
GAP_REASON_PARTIAL_WARMUP = "partial_warmup"


def build_feature_rows(candles: list[OHLCV], indicator_sets: list[ComputedIndicatorSet]) -> list[FeatureRow]:
    """Join raw candles with computed indicator values in timestamp order."""
    if len(candles) != len(indicator_sets):
        raise FeatureGapError("Candles and indicator rows must have the same length.")

    rows: list[FeatureRow] = []
    for candle, indicator_set in zip(candles, indicator_sets, strict=True):
        if candle.open_time != indicator_set.open_time:
            raise FeatureGapError("Computed indicator rows must align exactly with candle timestamps.")
        rows.append(FeatureRow.from_components(candle, indicator_set))

    return rows


def build_feature_window(
    rows: list[FeatureRow],
    *,
    symbol: str,
    interval: str,
    window_size: int,
    required_features: tuple[str, ...] = (),
) -> FeatureWindow:
    """Build the latest canonical feature window for one symbol."""
    if window_size < 1:
        raise IncompleteWindowError("`window_size` must be positive.")

    normalized_symbol = normalize_symbol(symbol)
    normalized_required_features = tuple(sorted(set(required_features)))
    if not rows:
        return FeatureWindow(
            symbol=normalized_symbol,
            interval=interval,
            rows=(),
            requested_features=normalized_required_features,
            is_complete=False,
            gap_reason=GAP_REASON_INSUFFICIENT_HISTORY,
        )

    _validate_rows(rows, normalized_symbol, interval)

    selected_rows = tuple(rows[-window_size:])
    if len(selected_rows) < window_size:
        return FeatureWindow(
            symbol=normalized_symbol,
            interval=interval,
            rows=selected_rows,
            requested_features=normalized_required_features,
            is_complete=False,
            gap_reason=GAP_REASON_INSUFFICIENT_HISTORY,
        )

    if not _rows_are_continuous(selected_rows, interval):
        return FeatureWindow(
            symbol=normalized_symbol,
            interval=interval,
            rows=selected_rows,
            requested_features=normalized_required_features,
            is_complete=False,
            gap_reason=GAP_REASON_MISSING_CANDLE_CONTINUITY,
        )

    if not all(_row_is_ready(row, normalized_required_features) for row in selected_rows):
        return FeatureWindow(
            symbol=normalized_symbol,
            interval=interval,
            rows=selected_rows,
            requested_features=normalized_required_features,
            is_complete=False,
            gap_reason=GAP_REASON_PARTIAL_WARMUP,
        )

    return FeatureWindow(
        symbol=normalized_symbol,
        interval=interval,
        rows=selected_rows,
        requested_features=normalized_required_features,
        is_complete=True,
        gap_reason=None,
    )


def _validate_rows(rows: list[FeatureRow], symbol: str, interval: str) -> None:
    """Validate identity and ordering for a feature-row series."""
    previous_open_time = rows[0].open_time
    for index, row in enumerate(rows):
        if row.symbol != symbol:
            raise FeatureValidationError("Feature rows must use one symbol.")
        if row.interval != interval:
            raise FeatureValidationError("Feature rows must use one interval.")
        if index == 0:
            continue
        if row.open_time <= previous_open_time:
            raise FeatureValidationError("Feature rows must be strictly ordered by open_time.")
        previous_open_time = row.open_time


def _rows_are_continuous(rows: tuple[FeatureRow, ...], interval: str) -> bool:
    """Check that a feature window has no candle gaps."""
    interval_delta = interval_to_timedelta(interval)
    for previous, current in zip(rows, rows[1:]):
        if current.open_time - previous.open_time != interval_delta:
            return False
    return True


def _row_is_ready(row: FeatureRow, required_features: tuple[str, ...]) -> bool:
    """Return whether a row satisfies the requested readiness policy."""
    if not required_features:
        return row.is_feature_ready
    return all(row.indicator_values.get(feature_name) is not None for feature_name in required_features)
