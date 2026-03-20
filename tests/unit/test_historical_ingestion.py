"""Unit tests for the historical ingestion service."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from capm.domains.market_data import HistoricalOHLCRequest, OHLCV
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


if __name__ == "__main__":
    unittest.main()
