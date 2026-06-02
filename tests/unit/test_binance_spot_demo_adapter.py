"""Unit tests for authenticated Binance Spot Demo trading."""

from __future__ import annotations

import unittest

import httpx

from capm.core.config import BinanceSettings
from capm.core.errors import ConfigurationError
from capm.domains.trading import DecisionAction, ProposedDecision
from capm.infra.exchange import BinanceSpotDemoTradingAdapter


class BinanceSpotDemoTradingAdapterTests(unittest.TestCase):
    def test_adapter_reads_balances_and_signs_request(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"balances": [{"asset": "USDT", "free": "50", "locked": "0"}, {"asset": "BTC", "free": "0.1", "locked": "0.02"}]})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 123,
        )

        portfolio = adapter.get_portfolio("BTCUSDT")

        self.assertEqual(portfolio.available_usdt, 50)
        self.assertEqual(portfolio.base_asset_free, 0.1)
        self.assertEqual(captured[0].headers["x-mbx-apikey"], "key")
        self.assertIn("signature=", str(captured[0].url))
        self.assertIn("timestamp=123", str(captured[0].url))

    def test_adapter_submits_market_buy_by_quote_amount(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"orderId": 1, "status": "FILLED"})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 123,
        )

        adapter.submit_market_order("BTCUSDT", ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=10))

        self.assertIn("quoteOrderQty=10", str(captured[0].url))
        self.assertEqual(captured[0].method, "POST")

    def test_adapter_refuses_live_host(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "refuses non-demo"):
            BinanceSpotDemoTradingAdapter(
                BinanceSettings(
                    mode="demo",
                    spot_rest_base_url="https://api.binance.com",
                    api_key="key",
                    api_secret="secret",
                )
            )
