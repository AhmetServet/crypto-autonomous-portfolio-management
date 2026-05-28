"""Unit tests for the historical ingestion service."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from capm.domains.market_data import CoverageRange, HistoricalOHLCRequest, OHLCV, OHLCVFetchPlan, TimeRange
from capm.services.ingestion import HistoricalMarketDataIngestionService


def make_candle(minute: int) -> OHLCV:
    """Create a predictable candle for tests."""
    return OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal("1.5"),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("150"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("60"),
        taker_buy_quote_asset_volume=Decimal("90"),
    )


class FakeHistoricalMarketDataPort:
    """Test double that serves deterministic pages."""

    def __init__(self, pages: list[list[OHLCV]]) -> None:
        self._pages = list(pages)
        self.calls: list[dict[str, object]] = []

    def fetch_ohlcv_page(self, **kwargs: object) -> list[OHLCV]:
        self.calls.append(kwargs)
        if not self._pages:
            return []
        return self._pages.pop(0)


class FakeMarketDataRepository:
    """Test double that captures persisted candle batches."""

    def __init__(
        self,
        *,
        stored_candles: list[OHLCV] | None = None,
        fetch_plan: OHLCVFetchPlan | None = None,
    ) -> None:
        self.saved_batches: list[list[OHLCV]] = []
        self.stored_candles = list(stored_candles or [])
        self.fetch_plan = fetch_plan

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        self.saved_batches.append(list(candles))
        self.stored_candles.extend(candles)

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        matching = [candle.open_time for candle in self.stored_candles if candle.symbol == symbol and candle.interval == interval]
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
            for candle in self.stored_candles
            if candle.symbol == symbol
            and candle.interval == interval
            and candle.open_time >= start_time
            and candle.open_time < end_time
        ]

    def plan_candle_fetch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> OHLCVFetchPlan:
        if self.fetch_plan is not None:
            return self.fetch_plan
        return OHLCVFetchPlan(
            covered_ranges=(),
            missing_ranges=(TimeRange(start_time, end_time),),
        )

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        for candle in self.stored_candles:
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


class HistoricalMarketDataIngestionServiceTests(unittest.TestCase):
    """Exercise multi-page retrieval behavior."""

    def test_service_fetches_all_pages_without_duplicates(self) -> None:
        port = FakeHistoricalMarketDataPort(
            pages=[
                [make_candle(0), make_candle(1)],
                [make_candle(2)],
            ]
        )
        service = HistoricalMarketDataIngestionService(market_data_port=port)

        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTC/USDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
            )
        )

        self.assertEqual([candle.open_time.minute for candle in candles], [0, 1, 2])
        self.assertEqual(port.calls[0]["limit"], 3)
        self.assertEqual(
            port.calls[1]["start_at"],
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )

    def test_service_persists_only_filtered_and_deduplicated_candles(self) -> None:
        port = FakeHistoricalMarketDataPort(
            pages=[
                [
                    make_candle(0),
                    make_candle(1),
                    make_candle(1),
                    make_candle(3),
                ]
            ]
        )
        repository = FakeMarketDataRepository()
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
        )

        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
            )
        )

        self.assertEqual([candle.open_time.minute for candle in candles], [0, 1])
        self.assertEqual(len(repository.saved_batches), 1)
        self.assertEqual(
            [candle.open_time.minute for candle in repository.saved_batches[0]],
            [0, 1],
        )

    def test_service_batches_persistence_across_multiple_exchange_pages(self) -> None:
        port = FakeHistoricalMarketDataPort(
            pages=[
                [make_candle(0), make_candle(1)],
                [make_candle(2), make_candle(3)],
                [make_candle(4), make_candle(5)],
            ]
        )
        repository = FakeMarketDataRepository()
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
            persist_batch_candle_count=4,
        )

        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 6, 0, tzinfo=UTC),
            )
        )

        self.assertEqual([candle.open_time.minute for candle in candles], [0, 1, 2, 3, 4, 5])
        self.assertEqual(len(repository.saved_batches), 2)
        self.assertEqual(
            [[candle.open_time.minute for candle in batch] for batch in repository.saved_batches],
            [[0, 1, 2, 3], [4, 5]],
        )

    def test_service_uses_db_only_when_request_is_fully_covered(self) -> None:
        repository = FakeMarketDataRepository(
            stored_candles=[make_candle(0), make_candle(1)],
            fetch_plan=OHLCVFetchPlan(
                covered_ranges=(
                    CoverageRange(
                        coinpair_id=1,
                        table_name="coinpair_1_ohlcv",
                        symbol="BTCUSDT",
                        interval="1m",
                        start_open_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                        end_open_time=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
                    ),
                ),
                missing_ranges=(),
            ),
        )
        port = FakeHistoricalMarketDataPort(pages=[])
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
        )

        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
            )
        )

        self.assertEqual([candle.open_time.minute for candle in candles], [0, 1])
        self.assertEqual(port.calls, [])
        self.assertEqual(repository.saved_batches, [])

    def test_service_fetches_only_missing_gap_when_db_is_partially_covered(self) -> None:
        repository = FakeMarketDataRepository(
            stored_candles=[make_candle(0), make_candle(1)],
            fetch_plan=OHLCVFetchPlan(
                covered_ranges=(
                    CoverageRange(
                        coinpair_id=1,
                        table_name="coinpair_1_ohlcv",
                        symbol="BTCUSDT",
                        interval="1m",
                        start_open_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                        end_open_time=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
                    ),
                ),
                missing_ranges=(
                    TimeRange(
                        datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
                        datetime(2024, 1, 1, 0, 4, 0, tzinfo=UTC),
                    ),
                ),
            ),
        )
        port = FakeHistoricalMarketDataPort(pages=[[make_candle(2), make_candle(3)]])
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
        )

        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 4, 0, tzinfo=UTC),
            )
        )

        self.assertEqual([candle.open_time.minute for candle in candles], [0, 1, 2, 3])
        self.assertEqual(len(port.calls), 1)
        self.assertEqual(port.calls[0]["start_at"], datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC))
        self.assertEqual(port.calls[0]["end_at"], datetime(2024, 1, 1, 0, 4, 0, tzinfo=UTC))
        self.assertEqual(len(repository.saved_batches), 1)
        self.assertEqual(
            [candle.open_time.minute for candle in repository.saved_batches[0]],
            [2, 3],
        )

    def test_service_invokes_fetch_progress_after_each_exchange_page(self) -> None:
        port = FakeHistoricalMarketDataPort(
            pages=[
                [make_candle(0), make_candle(1)],
                [make_candle(2)],
            ]
        )
        service = HistoricalMarketDataIngestionService(market_data_port=port)
        progress_calls = 0

        def tally(_completed: int, _total: int, _at: datetime) -> None:
            nonlocal progress_calls
            progress_calls += 1

        service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTC/USDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 5, 0, 0, 0, tzinfo=UTC),
            ),
            on_fetch_progress=tally,
        )

        self.assertEqual(progress_calls, 2)

    def test_service_reports_fetch_progress_when_range_is_fully_in_db(self) -> None:
        repository = FakeMarketDataRepository(
            stored_candles=[make_candle(0), make_candle(1)],
            fetch_plan=OHLCVFetchPlan(
                covered_ranges=(
                    CoverageRange(
                        coinpair_id=1,
                        table_name="coinpair_1_ohlcv",
                        symbol="BTCUSDT",
                        interval="1m",
                        start_open_time=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                        end_open_time=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
                    ),
                ),
                missing_ranges=(),
            ),
        )
        port = FakeHistoricalMarketDataPort(pages=[])
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
        )
        progress_calls = 0

        def tally(_completed: int, _total: int, _at: datetime) -> None:
            nonlocal progress_calls
            progress_calls += 1

        service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
            ),
            on_fetch_progress=tally,
        )

        self.assertEqual(progress_calls, 1)

    def test_ingest_ohlcv_persists_missing_rows_without_returning_candles(self) -> None:
        repository = FakeMarketDataRepository(
            fetch_plan=OHLCVFetchPlan(
                covered_ranges=(),
                missing_ranges=(
                    TimeRange(
                        datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                        datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
                    ),
                ),
            )
        )
        port = FakeHistoricalMarketDataPort(pages=[[make_candle(0), make_candle(1)], [make_candle(2)]])
        service = HistoricalMarketDataIngestionService(
            market_data_port=port,
            repository_port=repository,
            persist_batch_candle_count=2,
        )

        result = service.ingest_ohlcv(
            HistoricalOHLCRequest(
                symbol="BTCUSDT",
                interval="1m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
            )
        )

        self.assertEqual(result.fetched_count, 3)
        self.assertEqual(result.stored_count, 3)
        self.assertEqual(
            [[candle.open_time.minute for candle in batch] for batch in repository.saved_batches],
            [[0, 1], [2]],
        )


if __name__ == "__main__":
    unittest.main()
