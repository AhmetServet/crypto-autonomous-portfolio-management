"""Unit tests for the Binance spot market-data adapter."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

import httpx

from capm.core.config import BinanceSettings
from capm.infra.exchange import BinanceSpotMarketDataAdapter


class BinanceSpotMarketDataAdapterTests(unittest.TestCase):
    """Verify request construction and payload mapping."""

    def test_fetch_ohlcv_page_builds_expected_request(self) -> None:
        captured: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            payload = [
                [
                    1704067200000,
                    "42000.0",
                    "42100.0",
                    "41950.0",
                    "42050.0",
                    "100.0",
                    1704067259999,
                    "4205000.0",
                    123,
                    "60.0",
                    "2523000.0",
                    "0",
                ]
            ]
            return httpx.Response(
                200,
                content=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://testnet.binance.vision",
        )
        adapter = BinanceSpotMarketDataAdapter(
            settings=BinanceSettings.from_env(mode="demo"),
            client=client,
        )

        candles = adapter.fetch_ohlcv_page(
            symbol="btc/usdt",
            interval="1m",
            start_at=datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            end_at=datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            limit=1,
        )

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].symbol, "BTCUSDT")
        self.assertEqual(candles[0].close_time, datetime(2024, 1, 1, 0, 0, 59, 999000, tzinfo=UTC))
        self.assertIn("symbol=BTCUSDT", captured["url"])
        self.assertIn("interval=1m", captured["url"])
        self.assertIn("limit=1", captured["url"])
        client.close()


if __name__ == "__main__":
    unittest.main()
