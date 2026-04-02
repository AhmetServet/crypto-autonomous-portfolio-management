"""Unit tests for the indicator and feature-window module."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import tempfile

from capm.domains.features import (
    GAP_REASON_INSUFFICIENT_HISTORY,
    GAP_REASON_MISSING_CANDLE_CONTINUITY,
    GAP_REASON_PARTIAL_WARMUP,
    IndicatorRegistry,
    IndicatorSpec,
)
from capm.domains.market_data import OHLCV
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.features import IndicatorPipelineService


def make_candle(minute: int, *, close: str, symbol: str = "BTCUSDT") -> OHLCV:
    """Create a predictable candle with a configurable close price."""
    return OHLCV(
        symbol=symbol,
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("100"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("50"),
        taker_buy_quote_asset_volume=Decimal("50"),
    )


class FakeMarketDataRepository:
    """Simple in-memory market-data repository for tests."""

    def __init__(self, candles: list[OHLCV]) -> None:
        self._candles = list(candles)

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        raise NotImplementedError

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        matching = [candle.open_time for candle in self._candles if candle.symbol == symbol and candle.interval == interval]
        return max(matching) if matching else None

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCV]:
        return [
            candle
            for candle in self._candles
            if candle.symbol == symbol
            and candle.interval == interval
            and candle.open_time >= start_time
            and candle.open_time < end_time
        ]

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        for candle in self._candles:
            if candle.symbol == symbol and candle.interval == interval and candle.open_time == open_time:
                return candle
        return None

    def delete_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        raise NotImplementedError


class FakeFeatureRepository:
    """Test double that captures persisted derived feature rows."""

    def __init__(self) -> None:
        self.saved_batches: list[list[object]] = []

    def save_indicator_batch(self, records: list[object]) -> None:
        self.saved_batches.append(list(records))

    def get_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[object]:
        raise NotImplementedError

    def delete_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        raise NotImplementedError


class IndicatorRegistryTests(unittest.TestCase):
    """Exercise indicator calculations and warm-up behavior."""

    def test_registry_computes_sma_and_rsi_with_explicit_warmup(self) -> None:
        candles = [make_candle(index, close=str(index + 1)) for index in range(6)]
        registry = IndicatorRegistry(
            specs=(
                IndicatorSpec(name="", kind="sma", parameters={"period": 3}),
                IndicatorSpec(name="", kind="rsi", parameters={"period": 2}),
            )
        )

        computed = registry.compute(candles)

        self.assertEqual(computed[0].values["sma_3_close"], None)
        self.assertEqual(computed[1].values["sma_3_close"], None)
        self.assertEqual(computed[2].values["sma_3_close"], Decimal("2"))
        self.assertEqual(computed[0].values["rsi_2_close"], None)
        self.assertEqual(computed[1].values["rsi_2_close"], None)
        self.assertEqual(computed[2].values["rsi_2_close"], Decimal("100"))
        self.assertFalse(computed[1].is_ready)
        self.assertTrue(computed[-1].is_ready)

    def test_registry_computes_macd_and_bollinger_feature_names(self) -> None:
        candles = [make_candle(index, close=str(index + 1)) for index in range(40)]
        registry = IndicatorRegistry(
            specs=(
                IndicatorSpec(
                    name="",
                    kind="macd",
                    parameters={"fast_period": 3, "slow_period": 6, "signal_period": 2},
                ),
                IndicatorSpec(
                    name="",
                    kind="bbands",
                    parameters={"period": 5, "stddev_multiplier": "2"},
                ),
            )
        )

        computed = registry.compute(candles)
        latest = computed[-1].values

        self.assertIn("macd_3_6_2_line", latest)
        self.assertIn("macd_3_6_2_signal", latest)
        self.assertIn("macd_3_6_2_histogram", latest)
        self.assertIn("bbands_5_2_middle", latest)
        self.assertIn("bbands_5_2_upper", latest)
        self.assertIn("bbands_5_2_lower", latest)
        self.assertIsNotNone(latest["macd_3_6_2_signal"])
        self.assertIsNotNone(latest["bbands_5_2_upper"])


class IndicatorPipelineServiceTests(unittest.TestCase):
    """Exercise orchestration and window assembly behavior."""

    def test_service_builds_complete_window_and_persists_indicator_rows(self) -> None:
        candles = [make_candle(index, close=str(index + 1)) for index in range(10)]
        feature_repository = FakeFeatureRepository()
        service = IndicatorPipelineService(
            market_data_repository=FakeMarketDataRepository(candles),
            feature_repository=feature_repository,
        )

        window = service.get_latest_window(
            symbol="BTCUSDT",
            interval="1m",
            end_time=datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC),
            window_size=3,
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
        )

        self.assertTrue(window.is_complete)
        self.assertEqual(window.window_size, 3)
        self.assertEqual([row.open_time.minute for row in window.rows], [7, 8, 9])
        self.assertEqual(len(feature_repository.saved_batches), 1)
        self.assertEqual(
            feature_repository.saved_batches[0][-1].values["sma_3_close"],
            Decimal("9"),
        )

    def test_service_marks_window_incomplete_when_history_is_too_short(self) -> None:
        candles = [make_candle(index, close=str(index + 1)) for index in range(3)]
        service = IndicatorPipelineService(
            market_data_repository=FakeMarketDataRepository(candles),
        )

        window = service.get_latest_window(
            symbol="BTCUSDT",
            interval="1m",
            end_time=datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
            window_size=4,
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
        )

        self.assertFalse(window.is_complete)
        self.assertEqual(window.gap_reason, GAP_REASON_INSUFFICIENT_HISTORY)

    def test_service_marks_gap_when_candle_series_is_not_continuous(self) -> None:
        candles = [
            make_candle(0, close="1"),
            make_candle(1, close="2"),
            make_candle(3, close="4"),
            make_candle(4, close="5"),
        ]
        service = IndicatorPipelineService(
            market_data_repository=FakeMarketDataRepository(candles),
        )

        window = service.get_latest_window(
            symbol="BTCUSDT",
            interval="1m",
            end_time=datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC),
            window_size=3,
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 2}),),
        )

        self.assertFalse(window.is_complete)
        self.assertEqual(window.gap_reason, GAP_REASON_MISSING_CANDLE_CONTINUITY)

    def test_service_marks_partial_warmup_when_required_feature_is_missing(self) -> None:
        candles = [make_candle(index, close=str(index + 1)) for index in range(3)]
        service = IndicatorPipelineService(
            market_data_repository=FakeMarketDataRepository(candles),
        )

        window = service.get_latest_window(
            symbol="BTCUSDT",
            interval="1m",
            end_time=datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
            window_size=2,
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
        )

        self.assertFalse(window.is_complete)
        self.assertEqual(window.gap_reason, GAP_REASON_PARTIAL_WARMUP)

    def test_service_reads_back_persisted_windows_from_db_repository(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / "features.sqlite3"
        repository = TimescaleMarketDataRepository(f"sqlite+pysqlite:///{database_path}")
        candles = [make_candle(index, close=str(index + 1)) for index in range(10)]
        repository.save_ohlcv_batch(candles)
        service = IndicatorPipelineService(
            market_data_repository=repository,
            feature_repository=repository,
            feature_window_reader=repository,
        )

        service.compute_feature_batch(
            symbol="BTCUSDT",
            interval="1m",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC),
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
        )
        window = service.get_latest_window(
            symbol="BTCUSDT",
            interval="1m",
            end_time=datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC),
            window_size=3,
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
        )

        self.assertTrue(window.is_complete)
        self.assertEqual([row.open_time.minute for row in window.rows], [7, 8, 9])
        self.assertEqual(window.rows[-1].indicator_values["sma_3_close"], Decimal("9"))

    def test_backfill_feature_range_processes_chunks_with_overlap(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / "backfill.sqlite3"
        repository = TimescaleMarketDataRepository(
            f"sqlite+pysqlite:///{database_path}",
            feature_write_batch_size=2,
        )
        candles = [make_candle(index, close=str(index + 1)) for index in range(10)]
        repository.save_ohlcv_batch(candles)
        service = IndicatorPipelineService(
            market_data_repository=repository,
            feature_repository=repository,
            feature_window_reader=repository,
        )

        result = service.backfill_feature_range(
            symbol="BTCUSDT",
            interval="1m",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC),
            indicator_specs=(IndicatorSpec(name="", kind="sma", parameters={"period": 3}),),
            chunk_candle_count=4,
        )
        row = repository.get_indicator_set(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 4, 0, tzinfo=UTC),
        )

        self.assertEqual(result.chunks_processed, 3)
        self.assertEqual(result.indicator_rows_persisted, 10)
        self.assertIsNotNone(row)
        self.assertEqual(row.values["sma_3_close"], Decimal("4"))

    def test_backfill_feature_range_resumes_from_latest_persisted_timestamp(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        database_path = Path(temp_dir.name) / "resume.sqlite3"
        repository = TimescaleMarketDataRepository(f"sqlite+pysqlite:///{database_path}")
        candles = [make_candle(index, close=str(index + 1)) for index in range(10)]
        repository.save_ohlcv_batch(candles)
        service = IndicatorPipelineService(
            market_data_repository=repository,
            feature_repository=repository,
            feature_window_reader=repository,
        )
        specs = (IndicatorSpec(name="", kind="sma", parameters={"period": 3}),)

        service.backfill_feature_range(
            symbol="BTCUSDT",
            interval="1m",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 0, 6, 0, tzinfo=UTC),
            indicator_specs=specs,
            chunk_candle_count=3,
        )
        resumed = service.backfill_feature_range(
            symbol="BTCUSDT",
            interval="1m",
            start_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 0, 10, 0, tzinfo=UTC),
            indicator_specs=specs,
            chunk_candle_count=3,
        )
        latest = repository.get_latest_indicator_time("BTCUSDT", "1m")

        self.assertEqual(resumed.resumed_from, datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC))
        self.assertIsNotNone(latest)
        self.assertEqual(latest, datetime(2024, 1, 1, 0, 9, 0, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
