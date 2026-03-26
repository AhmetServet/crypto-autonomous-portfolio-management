"""Historical market-data ingestion flow."""

from __future__ import annotations

import math
from dataclasses import dataclass

from capm.core.contracts import HistoricalMarketDataPort, MarketDataRepositoryPort
from capm.core.errors import PaginationError
from capm.domains.market_data import HistoricalOHLCRequest, OHLCV


@dataclass(slots=True)
class HistoricalMarketDataIngestionService:
    """Fetches historical candles across exchange page boundaries."""

    market_data_port: HistoricalMarketDataPort
    repository_port: MarketDataRepositoryPort | None = None

    def fetch_ohlcv(self, request: HistoricalOHLCRequest) -> list[OHLCV]:
        """Retrieve candles for the full requested range."""
        candles: list[OHLCV] = []
        seen_open_times = set()
        cursor = request.start_at

        while cursor < request.end_at:
            remaining = request.end_at - cursor
            remaining_candles = max(
                1,
                math.ceil(remaining / request.interval_delta),
            )
            limit = min(request.max_records_per_page, remaining_candles)

            page = self.market_data_port.fetch_ohlcv_page(
                symbol=request.symbol,
                interval=request.interval,
                start_at=cursor,
                end_at=request.end_at,
                limit=limit,
            )
            if not page:
                break

            next_cursor = page[-1].open_time + request.interval_delta
            if next_cursor <= cursor:
                raise PaginationError(
                    "Historical market-data pagination did not advance. "
                    "Refusing to continue to avoid an infinite loop."
                )

            persisted_page: list[OHLCV] = []
            for candle in page:
                if candle.open_time < request.start_at or candle.open_time >= request.end_at:
                    continue
                if candle.open_time in seen_open_times:
                    continue
                candles.append(candle)
                persisted_page.append(candle)
                seen_open_times.add(candle.open_time)

            if self.repository_port and persisted_page:
                self.repository_port.save_ohlcv_batch(persisted_page)

            cursor = next_cursor

        return candles
