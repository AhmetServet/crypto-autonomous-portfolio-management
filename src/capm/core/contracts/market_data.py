"""Contracts for historical market-data ingestion."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from capm.domains.market_data import OHLCV


class HistoricalMarketDataPort(Protocol):
    """Abstracts historical OHLC retrieval behind a stable interface."""

    def fetch_ohlcv_page(
        self,
        *,
        symbol: str,
        interval: str,
        start_at: datetime,
        end_at: datetime | None = None,
        limit: int = 1000,
    ) -> list[OHLCV]:
        """Fetch one ascending page of candles from the exchange."""


class MarketDataRepositoryPort(Protocol):
    """Abstracts the storage mechanism for OHLCV data."""

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Create or update a batch of OHLCV candles to the database."""

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the open_time of the latest stored candle for a symbol and interval."""
        
    def get_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> list[OHLCV]:
        """Read candles for a given symbol, interval, and exact time window."""
        
    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        """Read a single precise candle based on its composite primary key."""
        
    def delete_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> int:
        """Delete candles for a given symbol, interval, and time window. Returns number of rows deleted."""
