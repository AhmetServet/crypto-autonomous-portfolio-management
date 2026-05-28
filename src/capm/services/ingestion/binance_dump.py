"""Binance public data dump ingestion for historical klines."""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Iterable

import httpx

from capm.core.contracts import MarketDataRepositoryPort
from capm.domains.market_data import HistoricalOHLCRequest, OHLCV, normalize_symbol
from capm.domains.market_data.entities import ensure_utc
from capm.infra.exchange import BinanceSpotMarketDataAdapter
from capm.services.ingestion.historical import HistoricalMarketDataIngestionService

BINANCE_PUBLIC_DATA_BASE_URL = "https://data.binance.vision"


@dataclass(frozen=True, slots=True)
class DumpIngestionResult:
    """Summary for a Binance public dump ingestion run."""

    symbol: str
    interval: str
    start_at: datetime
    end_at: datetime
    downloaded_files: int
    skipped_files: int
    coverage_skipped_files: int
    dump_rows: int
    rest_rows: int
    stored_rows: int
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class Month:
    """Calendar month address used by Binance public data paths."""

    year: int
    month: int

    @property
    def key(self) -> str:
        """Return Binance's YYYY-MM filename fragment."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def starts_at(self) -> datetime:
        """Return the first instant of the month in UTC."""
        return datetime(self.year, self.month, 1, tzinfo=UTC)

    @property
    def next_month(self) -> "Month":
        """Return the following calendar month."""
        if self.month == 12:
            return Month(self.year + 1, 1)
        return Month(self.year, self.month + 1)


def iter_months(start_at: datetime, end_at: datetime) -> Iterable[Month]:
    """Yield calendar months overlapping a half-open time range."""
    cursor = Month(ensure_utc(start_at).year, ensure_utc(start_at).month)
    normalized_end = ensure_utc(end_at)
    while cursor.starts_at < normalized_end:
        yield cursor
        cursor = cursor.next_month


class BinancePublicDumpIngestionService:
    """Download Binance public monthly kline ZIPs and persist matching rows."""

    def __init__(
        self,
        *,
        repository_port: MarketDataRepositoryPort,
        rest_adapter: BinanceSpotMarketDataAdapter | None = None,
        client: httpx.Client | None = None,
        base_url: str = BINANCE_PUBLIC_DATA_BASE_URL,
        persist_batch_candle_count: int = 50_000,
    ) -> None:
        """Initialize the dump ingestion service."""
        self.repository_port = repository_port
        self.rest_adapter = rest_adapter
        self.base_url = base_url.rstrip("/")
        self.persist_batch_candle_count = persist_batch_candle_count
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=60.0, follow_redirects=True)

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_client:
            self.client.close()

    def ingest_ohlcv(
        self,
        request: HistoricalOHLCRequest,
        *,
        include_rest_tail: bool = True,
    ) -> DumpIngestionResult:
        """Persist dump-backed candles and optionally fill missing ranges with REST."""
        started = perf_counter()
        downloaded_files = 0
        skipped_files = 0
        coverage_skipped_files = 0
        dump_rows = 0
        rest_rows = 0

        for month in iter_months(request.start_at, request.end_at):
            month_start = max(request.start_at, month.starts_at)
            month_end = min(request.end_at, month.next_month.starts_at)
            fetch_plan = self.repository_port.plan_candle_fetch(
                request.symbol,
                request.interval,
                month_start,
                month_end,
            )
            if fetch_plan.is_fully_covered:
                coverage_skipped_files += 1
                continue

            status, content = self._download_month(request.symbol, request.interval, month)
            if status == 404:
                skipped_files += 1
                continue
            if status >= 400:
                response_url = self._monthly_zip_url(request.symbol, request.interval, month)
                raise RuntimeError(f"Binance public data download failed with status {status}: {response_url}")

            downloaded_files += 1
            candles = list(self._parse_month_zip(content, request, month))
            dump_rows += len(candles)
            self._persist_candles(candles)

        if include_rest_tail and self.rest_adapter is not None:
            rest_service = HistoricalMarketDataIngestionService(
                market_data_port=self.rest_adapter,
                repository_port=self.repository_port,
                persist_batch_candle_count=self.persist_batch_candle_count,
            )
            rest_result = rest_service.ingest_ohlcv(request)
            rest_rows = rest_result.stored_count

        elapsed = perf_counter() - started
        return DumpIngestionResult(
            symbol=request.symbol,
            interval=request.interval,
            start_at=request.start_at,
            end_at=request.end_at,
            downloaded_files=downloaded_files,
            skipped_files=skipped_files,
            coverage_skipped_files=coverage_skipped_files,
            dump_rows=dump_rows,
            rest_rows=rest_rows,
            stored_rows=dump_rows + rest_rows,
            elapsed_seconds=elapsed,
        )

    def _download_month(self, symbol: str, interval: str, month: Month) -> tuple[int, bytes]:
        """Download one monthly ZIP and return status plus body."""
        response = self.client.get(self._monthly_zip_url(symbol, interval, month))
        return response.status_code, response.content

    def _monthly_zip_url(self, symbol: str, interval: str, month: Month) -> str:
        """Return the direct Binance public data ZIP URL for one month."""
        normalized_symbol = normalize_symbol(symbol)
        filename = f"{normalized_symbol}-{interval}-{month.key}.zip"
        return (
            f"{self.base_url}/data/spot/monthly/klines/"
            f"{normalized_symbol}/{interval}/{filename}"
        )

    def _parse_month_zip(
        self,
        content: bytes,
        request: HistoricalOHLCRequest,
        month: Month,
    ) -> Iterable[OHLCV]:
        """Parse one monthly kline ZIP into filtered domain candles."""
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            csv_names = [name for name in archive.namelist() if name.endswith(".csv")]
            if not csv_names:
                return
            with archive.open(csv_names[0]) as csv_file:
                text_file = io.TextIOWrapper(csv_file, encoding="utf-8", newline="")
                reader = csv.reader(text_file)
                for row in reader:
                    candle = self._row_to_candle(row, request.symbol, request.interval)
                    if candle is None:
                        continue
                    if candle.open_time < request.start_at or candle.open_time >= request.end_at:
                        continue
                    if candle.open_time < month.starts_at or candle.open_time >= month.next_month.starts_at:
                        continue
                    yield candle

    @staticmethod
    def _row_to_candle(row: list[str], symbol: str, interval: str) -> OHLCV | None:
        """Convert a Binance dump CSV row into an OHLCV candle."""
        if len(row) < 11 or not row[0].isdigit():
            return None

        return OHLCV(
            symbol=normalize_symbol(symbol),
            interval=interval,
            open_time=BinancePublicDumpIngestionService._timestamp_to_datetime(row[0]),
            open=Decimal(row[1]),
            high=Decimal(row[2]),
            low=Decimal(row[3]),
            close=Decimal(row[4]),
            volume=Decimal(row[5]),
            close_time=BinancePublicDumpIngestionService._timestamp_to_datetime(row[6]),
            quote_asset_volume=Decimal(row[7]),
            trade_count=int(row[8]),
            taker_buy_base_asset_volume=Decimal(row[9]),
            taker_buy_quote_asset_volume=Decimal(row[10]),
        )

    @staticmethod
    def _timestamp_to_datetime(value: str) -> datetime:
        """Convert Binance dump timestamps in milliseconds or microseconds to UTC."""
        timestamp = int(value)
        divisor = 1_000_000 if timestamp >= 10_000_000_000_000 else 1_000
        return datetime.fromtimestamp(timestamp / divisor, tz=UTC)

    def _persist_candles(self, candles: list[OHLCV]) -> None:
        """Persist candles in bounded batches."""
        for start_index in range(0, len(candles), self.persist_batch_candle_count):
            self.repository_port.save_ohlcv_batch(
                candles[start_index : start_index + self.persist_batch_candle_count]
            )
