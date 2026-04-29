"""Historical market-data ingestion flow."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from capm.core.contracts import HistoricalMarketDataPort, MarketDataRepositoryPort
from capm.core.errors import PaginationError
from capm.domains.market_data import HistoricalOHLCRequest, OHLCV

FetchProgressCallback = Callable[[int, int, datetime], None]


def _fetch_day_progress(request: HistoricalOHLCRequest, cursor: datetime) -> tuple[int, int]:
    """Map cursor position within the request window to completed/total day counts for progress UI."""
    start, end = request.start_at, request.end_at
    span_sec = (end - start).total_seconds()
    if span_sec <= 0:
        return 1, 1
    total_days = max(1, math.ceil(span_sec / 86400))
    done_sec = (min(max(cursor, start), end) - start).total_seconds()
    completed = min(total_days, max(0, int((done_sec / span_sec) * total_days)))
    return completed, total_days


@dataclass(slots=True)
class HistoricalMarketDataIngestionService:
    """Fetches historical candles across exchange page boundaries."""

    market_data_port: HistoricalMarketDataPort
    repository_port: MarketDataRepositoryPort | None = None
    persist_batch_candle_count: int = 10_000

    def __post_init__(self) -> None:
        """Validate ingestion write-buffer settings."""
        if self.persist_batch_candle_count < 1:
            raise ValueError("`persist_batch_candle_count` must be at least 1.")

    def fetch_ohlcv(
        self,
        request: HistoricalOHLCRequest,
        *,
        on_fetch_progress: FetchProgressCallback | None = None,
    ) -> list[OHLCV]:
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
                self._fetch_gap_into_cache(
                    request,
                    missing_range.start_time,
                    missing_range.end_time,
                    candles_by_open_time,
                    on_fetch_progress,
                )
            if on_fetch_progress is not None and not fetch_plan.missing_ranges:
                completed_days, total_days = _fetch_day_progress(request, request.end_at)
                on_fetch_progress(completed_days, total_days, request.end_at)
            candles = [candles_by_open_time[open_time] for open_time in sorted(candles_by_open_time)]
        else:
            self._fetch_gap_into_cache(
                request,
                request.start_at,
                request.end_at,
                candles_by_open_time,
                on_fetch_progress,
            )
            candles = [candles_by_open_time[open_time] for open_time in sorted(candles_by_open_time)]

        return candles

    def _fetch_gap_into_cache(
        self,
        request: HistoricalOHLCRequest,
        start_time: datetime,
        end_time: datetime,
        candles_by_open_time: dict[datetime, OHLCV],
        on_fetch_progress: FetchProgressCallback | None,
    ) -> None:
        """Fetch one missing gap from the exchange and merge it into the result cache."""
        cursor = start_time
        pending_persist_batch: list[OHLCV] = []
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

            for candle in page:
                if candle.open_time < start_time or candle.open_time >= end_time:
                    continue
                if candle.open_time in candles_by_open_time:
                    continue
                candles_by_open_time[candle.open_time] = candle
                if self.repository_port is not None:
                    pending_persist_batch.append(candle)
                    if len(pending_persist_batch) >= self.persist_batch_candle_count:
                        self.repository_port.save_ohlcv_batch(pending_persist_batch)
                        pending_persist_batch = []

            cursor = next_cursor
            if on_fetch_progress is not None:
                completed_days, total_days = _fetch_day_progress(request, cursor)
                progress_at = min(cursor, request.end_at)
                on_fetch_progress(completed_days, total_days, progress_at)

        if self.repository_port is not None and pending_persist_batch:
            self.repository_port.save_ohlcv_batch(pending_persist_batch)
