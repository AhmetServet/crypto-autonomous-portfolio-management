"""Domain models for OHLC market data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from capm.core.errors import ValidationError

SUPPORTED_INTERVALS: dict[str, timedelta] = {
    "1s": timedelta(seconds=1),
    "1m": timedelta(minutes=1),
    "3m": timedelta(minutes=3),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "6h": timedelta(hours=6),
    "8h": timedelta(hours=8),
    "12h": timedelta(hours=12),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
}


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime into a timezone-aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_symbol(symbol: str) -> str:
    """Normalize `BTC/USDT`-style symbols to Binance's `BTCUSDT` format."""
    normalized = symbol.strip().upper().replace("/", "").replace("-", "").replace("_", "")
    if not normalized or not normalized.isalnum():
        raise ValidationError(f"Invalid trading pair {symbol!r}.")
    return normalized


def interval_to_timedelta(interval: str) -> timedelta:
    """Resolve a Binance interval into a timedelta."""
    if interval not in SUPPORTED_INTERVALS:
        raise ValidationError(
            f"Unsupported interval {interval!r}. "
            f"Expected one of {sorted(SUPPORTED_INTERVALS)}."
        )
    return SUPPORTED_INTERVALS[interval]


@dataclass(frozen=True, slots=True)
class HistoricalOHLCRequest:
    """Validated request for historical OHLC retrieval."""

    symbol: str
    interval: str
    start_at: datetime
    end_at: datetime
    max_records_per_page: int = 1000

    def __post_init__(self) -> None:
        """Validate and normalize the request."""
        normalized_symbol = normalize_symbol(self.symbol)
        normalized_start = ensure_utc(self.start_at)
        normalized_end = ensure_utc(self.end_at)
        interval_to_timedelta(self.interval)

        if normalized_start >= normalized_end:
            raise ValidationError("`start_at` must be earlier than `end_at`.")
        if not 1 <= self.max_records_per_page <= 1000:
            raise ValidationError("`max_records_per_page` must be between 1 and 1000.")

        object.__setattr__(self, "symbol", normalized_symbol)
        object.__setattr__(self, "start_at", normalized_start)
        object.__setattr__(self, "end_at", normalized_end)

    @property
    def interval_delta(self) -> timedelta:
        """Return the duration represented by the requested interval."""
        return interval_to_timedelta(self.interval)


@dataclass(frozen=True, slots=True)
class OHLCV:
    """Canonical OHLCV candle used throughout the application."""

    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_asset_volume: Decimal
    trade_count: int
    taker_buy_base_asset_volume: Decimal
    taker_buy_quote_asset_volume: Decimal

    def to_dict(self) -> dict[str, str | int]:
        """Serialize the candle into JSON-friendly values."""
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "quote_asset_volume": str(self.quote_asset_volume),
            "trade_count": self.trade_count,
            "taker_buy_base_asset_volume": str(self.taker_buy_base_asset_volume),
            "taker_buy_quote_asset_volume": str(self.taker_buy_quote_asset_volume),
        }
