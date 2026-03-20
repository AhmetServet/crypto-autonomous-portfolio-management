"""Unit tests for market-data domain models."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.core.errors import ValidationError
from capm.domains.market_data import HistoricalOHLCRequest


class HistoricalOHLCRequestTests(unittest.TestCase):
    """Exercise request validation and normalization."""

    def test_request_normalizes_symbol_and_timezone(self) -> None:
        request = HistoricalOHLCRequest(
            symbol="btc/usdt",
            interval="1m",
            start_at=datetime(2024, 1, 1, 0, 0, 0),
            end_at=datetime(2024, 1, 1, 0, 5, 0),
        )

        self.assertEqual(request.symbol, "BTCUSDT")
        self.assertEqual(request.start_at.tzinfo, UTC)
        self.assertEqual(request.end_at.tzinfo, UTC)

    def test_request_rejects_unsupported_intervals(self) -> None:
        with self.assertRaises(ValidationError):
            HistoricalOHLCRequest(
                symbol="ETHUSDT",
                interval="7m",
                start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
                end_at=datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC),
            )


if __name__ == "__main__":
    unittest.main()
