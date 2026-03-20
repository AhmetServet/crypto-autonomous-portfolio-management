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
