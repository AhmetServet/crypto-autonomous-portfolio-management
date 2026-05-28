"""Unit tests for Binance public dump ingestion."""

from __future__ import annotations

import io
import unittest
import zipfile
from datetime import UTC, datetime

import httpx

from capm.domains.market_data import HistoricalOHLCRequest, OHLCVFetchPlan, TimeRange
from capm.services.ingestion.binance_dump import BinancePublicDumpIngestionService


class FakeRepository:
    """Capture persisted dump candles."""

    def __init__(self) -> None:
        self.saved_batches = []

    def save_ohlcv_batch(self, candles):
        self.saved_batches.append(list(candles))

    def get_latest_candle_time(self, symbol, interval):
        return None

    def get_candles(self, symbol, interval, start_time, end_time):
        return []

    def plan_candle_fetch(self, symbol, interval, start_time, end_time):
        return OHLCVFetchPlan(covered_ranges=(), missing_ranges=(TimeRange(start_time, end_time),))

    def get_candle(self, symbol, interval, open_time):
        return None

    def delete_candles(self, symbol, interval, start_time, end_time):
        return 0


def build_zip(csv_text: str) -> bytes:
    """Build an in-memory ZIP containing one CSV file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("BTCUSDT-1m-2024-01.csv", csv_text)
    return buffer.getvalue()


class BinancePublicDumpIngestionServiceTests(unittest.TestCase):
    """Exercise public dump parsing and persistence behavior."""

    def test_dump_ingestion_downloads_filters_and_persists_monthly_rows(self) -> None:
        csv_payload = "\n".join(
            [
                "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_base,taker_quote,ignore",
                "1704067200000,1,2,0.5,1.5,100,1704067259999,150,10,60,90,0",
                "1704067260000,2,3,1.5,2.5,200,1704067319999,300,11,70,95,0",
                "1704067320000,3,4,2.5,3.5,300,1704067379999,450,12,80,100,0",
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertIn("/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip", str(request.url))
            return httpx.Response(200, content=build_zip(csv_payload))

        repository = FakeRepository()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = BinancePublicDumpIngestionService(repository_port=repository, client=client, persist_batch_candle_count=2)

        result = service.ingest_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 3, tzinfo=UTC),
            ),
            include_rest_tail=False,
        )

        self.assertEqual(result.downloaded_files, 1)
        self.assertEqual(result.dump_rows, 2)
        self.assertEqual([[candle.open_time.minute for candle in batch] for batch in repository.saved_batches], [[1, 2]])

    def test_dump_ingestion_skips_unreleased_missing_month(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        repository = FakeRepository()
        client = httpx.Client(transport=httpx.MockTransport(handler))
        service = BinancePublicDumpIngestionService(repository_port=repository, client=client)

        result = service.ingest_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2026, 5, 1, tzinfo=UTC),
                end_at=datetime(2026, 5, 26, tzinfo=UTC),
            ),
            include_rest_tail=False,
        )

        self.assertEqual(result.downloaded_files, 0)
        self.assertEqual(result.skipped_files, 1)
        self.assertEqual(repository.saved_batches, [])

    def test_dump_parser_accepts_microsecond_timestamps(self) -> None:
        candle = BinancePublicDumpIngestionService._row_to_candle(
            [
                "1730419200000000",
                "1",
                "2",
                "0.5",
                "1.5",
                "100",
                "1730419259999000",
                "150",
                "10",
                "60",
                "90",
            ],
            "BTCUSDT",
            "1m",
        )

        self.assertIsNotNone(candle)
        assert candle is not None
        self.assertEqual(candle.open_time, datetime(2024, 11, 1, 0, 0, tzinfo=UTC))
        self.assertEqual(candle.close_time, datetime(2024, 11, 1, 0, 0, 59, 999000, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
