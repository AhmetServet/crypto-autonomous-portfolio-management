"""Unit tests for the provider-compatible LLM decision policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import unittest

import httpx

from capm.core.config import LLMSettings
from capm.domains.market_data import OHLCV
from capm.domains.trading import DecisionRequest, PortfolioSnapshot, RiskConfig
from capm.services.llm_decision_policy import LLMDecisionPolicy


def _request(symbol: str) -> DecisionRequest:
    open_time = datetime(2024, 1, 1, tzinfo=UTC)
    return DecisionRequest(
        cycle_id=f"{open_time.isoformat()}:{symbol}:1m:dry_run",
        mode="dry_run",
        symbol=symbol,
        interval="1m",
        reference_time=open_time,
        latest_candle=OHLCV(
            symbol=symbol,
            interval="1m",
            open_time=open_time,
            close_time=open_time + timedelta(minutes=1),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1"),
            quote_asset_volume=Decimal("100"),
            trade_count=1,
            taker_buy_base_asset_volume=Decimal("1"),
            taker_buy_quote_asset_volume=Decimal("100"),
        ),
        recent_candles=(),
        indicators={"rsi_14_close": "55"},
        predictions=(),
        portfolio=PortfolioSnapshot(available_usdt=1000.0),
        risk_config=RiskConfig(),
    )


class LLMDecisionPolicyTests(unittest.TestCase):
    """Exercise batched calls and malformed-response retries."""

    def test_policy_calls_configured_chat_completions_endpoint_once_for_all_symbols(self) -> None:
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200,
                json={
                    "usage": {"total_tokens": 12},
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    [
                                        {
                                            "symbol": "BTCUSDT",
                                            "action": "hold",
                                            "requested_usdt_amount": None,
                                            "requested_quantity": None,
                                            "confidence": 0.5,
                                            "reason": "wait",
                                        },
                                        {
                                            "symbol": "ETHUSDT",
                                            "action": "buy",
                                            "requested_usdt_amount": 10,
                                            "requested_quantity": None,
                                            "confidence": 0.7,
                                            "reason": "up signal",
                                        },
                                    ]
                                )
                            }
                        }
                    ]
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        policy = LLMDecisionPolicy(
            LLMSettings(api_key="secret", model="provider/model", base_url="https://provider.example/v1"),
            client=client,
        )

        result = policy.decide_batch((_request("BTCUSDT"), _request("ETHUSDT")))

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].url, httpx.URL("https://provider.example/v1/chat/completions"))
        self.assertEqual(captured[0].headers["authorization"], "Bearer secret")
        self.assertEqual(result.decisions["BTCUSDT"].action, "hold")
        self.assertEqual(result.decisions["ETHUSDT"].requested_usdt_amount, 10.0)
        self.assertIn("Return only a JSON array", result.system_prompt)
        self.assertEqual(result.provider_host, "provider.example")
        self.assertEqual(result.usage["total_tokens"], 12)

    def test_policy_retries_malformed_json(self) -> None:
        responses = iter(
            [
                {"choices": [{"message": {"content": "not-json"}}]},
                {
                    "choices": [
                        {
                            "message": {
                                "content": '[{"symbol":"BTCUSDT","action":"hold","requested_usdt_amount":null,'
                                '"requested_quantity":null,"confidence":0.4,"reason":"wait"}]'
                            }
                        }
                    ]
                },
            ]
        )
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=next(responses))))
        policy = LLMDecisionPolicy(LLMSettings(api_key="secret", model="model", retry_attempts=2), client=client)

        result = policy.decide_batch((_request("BTCUSDT"),))

        self.assertEqual(result.attempts, 2)

    def test_policy_rejects_hold_with_trade_amount(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {
                                    "content": '[{"symbol":"BTCUSDT","action":"hold",'
                                    '"requested_usdt_amount":10,"requested_quantity":null,'
                                    '"confidence":0.4,"reason":"wait"}]'
                                }
                            }
                        ]
                    },
                )
            )
        )
        policy = LLMDecisionPolicy(LLMSettings(api_key="secret", model="model", retry_attempts=1), client=client)

        with self.assertRaisesRegex(ValueError, "hold requires null amounts"):
            policy.decide_batch((_request("BTCUSDT"),))

    def test_policy_includes_provider_body_for_http_errors(self) -> None:
        client = httpx.Client(
            transport=httpx.MockTransport(lambda _request: httpx.Response(400, text='{"error":"bad model"}'))
        )
        policy = LLMDecisionPolicy(LLMSettings(api_key="secret", model="bad-model", retry_attempts=1), client=client)

        with self.assertRaisesRegex(ValueError, "bad model"):
            policy.decide_batch((_request("BTCUSDT"),))


if __name__ == "__main__":
    unittest.main()
