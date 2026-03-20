"""Binance spot market-data adapter."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Callable

import httpx

from capm.core.config import BinanceSettings
from capm.core.errors import ExchangeAPIError, ValidationError
from capm.domains.market_data import OHLCV, interval_to_timedelta, normalize_symbol


@dataclass(slots=True)
class BinanceSpotMarketDataAdapter:
    """REST adapter for Binance spot OHLC retrieval."""

    settings: BinanceSettings
    client: httpx.Client | None = None
    sleep: Callable[[float], None] = time.sleep
    _owns_client: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Create the HTTP client when one is not injected."""
        self._owns_client = self.client is None
        if self.client is None:
            self.client = httpx.Client(
                base_url=self.settings.spot_rest_base_url,
                timeout=self.settings.request_timeout_seconds,
                trust_env=self.settings.trust_env,
            )

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client and self.client is not None:
            self.client.close()

    def fetch_ohlcv_page(
        self,
        *,
        symbol: str,
        interval: str,
        start_at: datetime,
        end_at: datetime | None = None,
        limit: int = 1000,
    ) -> list[OHLCV]:
        """Fetch one page of Binance klines."""
        if not 1 <= limit <= self.settings.max_klines_per_request:
            raise ValidationError(
                f"`limit` must be between 1 and {self.settings.max_klines_per_request}."
            )

        normalized_symbol = normalize_symbol(symbol)
        interval_to_timedelta(interval)
        params: dict[str, Any] = {
            "symbol": normalized_symbol,
            "interval": interval,
            "startTime": self._to_milliseconds(start_at),
            "limit": limit,
        }
        if end_at is not None:
            params["endTime"] = self._to_milliseconds(end_at)

        payload = self._get_json("/api/v3/klines", params=params)
        return [
            self._map_kline(
                symbol=normalized_symbol,
                interval=interval,
                payload=entry,
            )
            for entry in payload
        ]

    def _get_json(self, path: str, *, params: dict[str, Any]) -> list[list[Any]]:
        """Execute a retried GET request against Binance."""
        assert self.client is not None

        last_error: Exception | None = None
        for attempt in range(1, self.settings.retry_attempts + 1):
            try:
                response = self.client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise ExchangeAPIError("Expected Binance klines response to be a list.")
                return payload
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                last_error = exc
                if 400 <= status_code < 500 and status_code != 429:
                    raise ExchangeAPIError(
                        f"Binance rejected the klines request with status {status_code}: "
                        f"{exc.response.text}"
                    ) from exc
            except httpx.RequestError as exc:
                last_error = exc

            if attempt < self.settings.retry_attempts:
                self.sleep(self.settings.retry_backoff_seconds * (2 ** (attempt - 1)))

        raise ExchangeAPIError("Binance klines request failed after retries.") from last_error

    @staticmethod
    def _map_kline(*, symbol: str, interval: str, payload: list[Any]) -> OHLCV:
        """Map a Binance kline payload into the domain candle model."""
        if len(payload) < 11:
            raise ExchangeAPIError("Unexpected Binance kline payload shape.")

        return OHLCV(
            symbol=symbol,
            interval=interval,
            open_time=datetime.fromtimestamp(payload[0] / 1000, tz=UTC),
            open=Decimal(str(payload[1])),
            high=Decimal(str(payload[2])),
            low=Decimal(str(payload[3])),
            close=Decimal(str(payload[4])),
            volume=Decimal(str(payload[5])),
            close_time=datetime.fromtimestamp(payload[6] / 1000, tz=UTC),
            quote_asset_volume=Decimal(str(payload[7])),
            trade_count=int(payload[8]),
            taker_buy_base_asset_volume=Decimal(str(payload[9])),
            taker_buy_quote_asset_volume=Decimal(str(payload[10])),
        )

    @staticmethod
    def _to_milliseconds(value: datetime) -> int:
        """Convert a datetime to a UTC millisecond timestamp."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return int(value.timestamp() * 1000)
