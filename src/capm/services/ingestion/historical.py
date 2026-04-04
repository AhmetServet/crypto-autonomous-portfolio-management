"""Historical market-data ingestion flow."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

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
        candles_by_open_time: dict[datetime, OHLCV] = {}
        if self.repository_port is not None:
            fetch_plan = self.repository_port.plan_candle_fetch(
                request.symbol,
                request.interval,
                request.start_at,
                request.end_at,
            )
            for covered_range in fetch_plan.covered_ranges:
                read_start = max(request.start_at, covered_range.start_open_time)
                read_end = min(request.end_at, covered_range.end_open_time + request.interval_delta)
                for candle in self.repository_port.get_candles(
                    request.symbol,
                    request.interval,
                    read_start,
                    read_end,
                ):
                    candles_by_open_time[candle.open_time] = candle

            for missing_range in fetch_plan.missing_ranges:
                self._fetch_gap_into_cache(request, missing_range.start_time, missing_range.end_time, candles_by_open_time)
            return [candles_by_open_time[open_time] for open_time in sorted(candles_by_open_time)]

        self._fetch_gap_into_cache(request, request.start_at, request.end_at, candles_by_open_time)
        return [candles_by_open_time[open_time] for open_time in sorted(candles_by_open_time)]

    def _fetch_gap_into_cache(
        self,
        request: HistoricalOHLCRequest,
        start_time: datetime,
        end_time: datetime,
        candles_by_open_time: dict[datetime, OHLCV],
    ) -> None:
        """Fetch one missing gap from the exchange and merge it into the result cache."""
        cursor = start_time
        while cursor < end_time:
            remaining = end_time - cursor
            remaining_candles = max(
                1,
                math.ceil(remaining / request.interval_delta),
            )
            limit = min(request.max_records_per_page, remaining_candles)

            page = self.market_data_port.fetch_ohlcv_page(
                symbol=request.symbol,
                interval=request.interval,
                start_at=cursor,
                end_at=end_time,
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
                if candle.open_time < start_time or candle.open_time >= end_time:
                    continue
                if candle.open_time in candles_by_open_time:
                    continue
                candles_by_open_time[candle.open_time] = candle
                persisted_page.append(candle)

            if self.repository_port and persisted_page:
                self.repository_port.save_ohlcv_batch(persisted_page)

            cursor = next_cursor
