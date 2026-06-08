"""Unit tests for authenticated Binance Spot Demo trading."""

from __future__ import annotations

import unittest

import httpx

from capm.core.config import BinanceSettings
from capm.core.errors import ConfigurationError, ValidationError
from capm.domains.trading import DecisionAction, ProposedDecision
from capm.infra.exchange import BinanceSpotDemoTradingAdapter


class BinanceSpotDemoTradingAdapterTests(unittest.TestCase):
    @staticmethod
    def _exchange_info() -> dict:
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "quoteOrderQtyMarketAllowed": True,
                    "filters": [
                        {
                            "filterType": "MARKET_LOT_SIZE",
                            "minQty": "0.00001000",
                            "maxQty": "100.00000000",
                            "stepSize": "0.00001000",
                        },
                        {"filterType": "MIN_NOTIONAL", "minNotional": "5.00000000"},
                    ],
                }
            ]
        }

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
            if request.url.path == "/api/v3/exchangeInfo":
                return httpx.Response(200, json=self._exchange_info())
            return httpx.Response(200, json={"orderId": 1, "status": "FILLED"})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 123,
        )

        adapter.submit_market_order("BTCUSDT", ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=10))

        self.assertIn("quoteOrderQty=10", str(captured[1].url))
        self.assertEqual(captured[1].method, "POST")

    def test_adapter_normalizes_market_sell_quantity_to_step_size(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.path == "/api/v3/exchangeInfo":
                return httpx.Response(200, json=self._exchange_info())
            return httpx.Response(200, json={"orderId": 1, "status": "FILLED"})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 123,
        )

        adapter.submit_market_order("BTCUSDT", ProposedDecision(action=DecisionAction.SELL, requested_quantity=0.000149))

        self.assertIn("quantity=0.00014000", str(captured[1].url))

    def test_adapter_falls_back_to_lot_size_when_market_lot_step_size_is_zero(self) -> None:
        captured = []
        exchange_info = self._exchange_info()
        exchange_info["symbols"][0]["filters"] = [
            {
                "filterType": "MARKET_LOT_SIZE",
                "minQty": "0.00000000",
                "maxQty": "100.00000000",
                "stepSize": "0.00000000",
            },
            {
                "filterType": "LOT_SIZE",
                "minQty": "0.00001000",
                "maxQty": "100.00000000",
                "stepSize": "0.00001000",
            },
            {"filterType": "MIN_NOTIONAL", "minNotional": "5.00000000"},
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if request.url.path == "/api/v3/exchangeInfo":
                return httpx.Response(200, json=exchange_info)
            return httpx.Response(200, json={"orderId": 1, "status": "FILLED"})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 123,
        )

        adapter.submit_market_order("BTCUSDT", ProposedDecision(action=DecisionAction.SELL, requested_quantity=0.000149))

        self.assertIn("quantity=0.00014000", str(captured[1].url))

    def test_adapter_rejects_buy_below_minimum_notional_before_order_request(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=self._exchange_info())

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
        )

        with self.assertRaisesRegex(ValidationError, "below minimum notional"):
            adapter.submit_market_order(
                "BTCUSDT",
                ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=4),
            )

        self.assertEqual([request.url.path for request in captured], ["/api/v3/exchangeInfo"])

    def test_adapter_reads_order_status_with_signed_request(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"orderId": 123, "status": "FILLED"})

        adapter = BinanceSpotDemoTradingAdapter(
            BinanceSettings(api_key="key", api_secret="secret"),
            client=httpx.Client(transport=httpx.MockTransport(handler), base_url="https://demo-api.binance.com"),
            now_ms=lambda: 456,
        )

        response = adapter.get_order("BTCUSDT", 123)

        self.assertEqual(response["status"], "FILLED")
        self.assertIn("orderId=123", str(captured[0].url))
        self.assertIn("timestamp=456", str(captured[0].url))
        self.assertIn("signature=", str(captured[0].url))

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
