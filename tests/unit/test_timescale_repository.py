"""Unit tests for the Timescale market-data repository."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect

from capm.domains.market_data import OHLCV
from capm.infra.database.models import get_ohlcv_model
from capm.infra.database.timescale import TimescaleMarketDataRepository


def make_candle(
    minute: int,
    *,
    symbol: str = "BTCUSDT",
    close: str = "1.5",
) -> OHLCV:
    """Create a predictable candle for repository tests."""
    return OHLCV(
        symbol=symbol,
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("150"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("60"),
        taker_buy_quote_asset_volume=Decimal("90"),
    )


class TimescaleMarketDataRepositoryTests(unittest.TestCase):
    """Exercise CRUD behavior for symbol-scoped OHLCV tables."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.repository = TimescaleMarketDataRepository(
            f"sqlite+pysqlite:///{database_path}"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_model_factory_round_trips_domain_entity(self) -> None:
        model = get_ohlcv_model("btc/usdt")
        candle = make_candle(0)

        mapped = model.from_domain(candle)

        self.assertEqual(mapped.to_domain(), candle)

    def test_repository_creates_symbol_tables_and_reads_back_ranges(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(0, symbol="ETHUSDT")])

        btc_candles = self.repository.get_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )
        eth_candle = self.repository.get_candle(
            "ETHUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        inspector = inspect(self.repository._engine)
        self.assertTrue(inspector.has_table("BTCUSDT"))
        self.assertTrue(inspector.has_table("ETHUSDT"))
        self.assertEqual([candle.open_time.minute for candle in btc_candles], [0, 1])
        self.assertIsNotNone(eth_candle)
        self.assertEqual(eth_candle.symbol, "ETHUSDT")

    def test_repository_upserts_existing_candle(self) -> None:
        candle = make_candle(0)
        updated = make_candle(0, close="9.9")

        self.repository.save_ohlcv_batch([candle])
        self.repository.save_ohlcv_batch([updated])

        stored = self.repository.get_candle("BTCUSDT", "1m", candle.open_time)

        self.assertIsNotNone(stored)
        self.assertEqual(stored.close, Decimal("9.9"))

    def test_repository_returns_latest_and_deletes_ranges(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(2)])

        latest = self.repository.get_latest_candle_time("BTCUSDT", "1m")
        deleted = self.repository.delete_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
        )
        remaining = self.repository.get_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
        )

        self.assertEqual(latest, datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC))
        self.assertEqual(deleted, 2)
        self.assertEqual([candle.open_time.minute for candle in remaining], [0])

    def test_repository_ignores_empty_batches(self) -> None:
        self.repository.save_ohlcv_batch([])

        self.assertIsNone(self.repository.get_latest_candle_time("BTCUSDT", "1m"))


if __name__ == "__main__":
    unittest.main()
