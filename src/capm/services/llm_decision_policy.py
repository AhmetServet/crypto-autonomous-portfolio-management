"""OpenAI-compatible LLM decision policy for batched trading decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

import httpx

from capm.core.config import LLMSettings
from capm.domains.trading import DecisionAction, DecisionRequest, ProposedDecision


@dataclass(frozen=True, slots=True)
class LLMDecisionBatch:
    """Parsed decisions plus audit metadata for one LLM call."""

    decisions: dict[str, ProposedDecision]
    system_prompt: str
    prompt: str
    raw_response: str
    attempts: int
    model: str
    provider_host: str
    latency_seconds: float
    usage: dict[str, Any]


class LLMDecisionPolicy:
    """Ask one OpenAI-compatible chat-completions endpoint for all symbol actions."""

    def __init__(self, settings: LLMSettings, *, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(timeout=settings.request_timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        """Close the internally-created HTTP client."""
        if self._owns_client:
            self.client.close()

    def decide_batch(self, requests: tuple[DecisionRequest, ...]) -> LLMDecisionBatch:
        """Return one validated LLM decision for every requested symbol."""
        if not requests:
            raise ValueError("At least one decision request is required.")
        system_prompt = self._system_prompt()
        prompt = self._build_prompt(requests)
        last_response = ""
        last_error = ""
        started_at = perf_counter()
        for attempt in range(1, self.settings.retry_attempts + 1):
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
            if last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Previous response was invalid: {last_error}. Return only valid JSON.",
                    }
                )
            response = self.client.post(
                f"{self.settings.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
                json={"model": self.settings.model, "messages": messages, "temperature": 0},
            )
            response.raise_for_status()
            payload = response.json()
            last_response = str(payload["choices"][0]["message"]["content"])
            try:
                decisions = self._parse_response(last_response, requests)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)
                continue
            return LLMDecisionBatch(
                decisions=decisions,
                system_prompt=system_prompt,
                prompt=prompt,
                raw_response=last_response,
                attempts=attempt,
                model=self.settings.model,
                provider_host=urlparse(self.settings.base_url).netloc,
                latency_seconds=perf_counter() - started_at,
                usage=dict(payload.get("usage") or {}),
            )
        raise ValueError(f"LLM returned invalid decisions after {self.settings.retry_attempts} attempts: {last_error}")

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a cautious crypto spot trading decision agent. "
            "Return only a JSON array. For every input symbol return exactly one object with keys: "
            "symbol, action, requested_usdt_amount, requested_quantity, confidence, reason. "
            "action must be buy, sell, or hold. Use null when an amount does not apply. "
            "This is spot trading only: never short sell. For buy set requested_usdt_amount and requested_quantity=null. "
            "For sell set requested_quantity and requested_usdt_amount=null. For hold set both amounts to null. "
            "confidence must be between 0 and 1. Do not bypass risk limits. "
            "Prefer hold when predictions are missing, stale, conflicting, or weak."
        )

    @staticmethod
    def _build_prompt(requests: tuple[DecisionRequest, ...]) -> str:
        payload = {
            "portfolio": requests[0].portfolio.to_dict(),
            "risk": {
                "max_trade_usdt": requests[0].risk_config.max_trade_usdt,
                "max_position_usdt": requests[0].risk_config.max_position_usdt,
            },
            "symbols": [
                {
                    "symbol": request.symbol,
                    "reference_time": request.reference_time.isoformat(),
                    "current_price": str(request.latest_candle.close),
                    "recent_candles": [
                        {
                            "open_time": candle.open_time.isoformat(),
                            "open": str(candle.open),
                            "high": str(candle.high),
                            "low": str(candle.low),
                            "close": str(candle.close),
                            "volume": str(candle.volume),
                        }
                        for candle in request.recent_candles
                    ],
                    "indicators": request.indicators,
                    "predictions": [
                        {
                            "model": row.model_name,
                            "predicted_return": row.predicted_return,
                            "predicted_direction": row.predicted_direction,
                            "prediction_time": row.prediction_time.isoformat(),
                            "prediction_age_minutes": (
                                request.reference_time - row.reference_time
                            ).total_seconds()
                            / 60,
                        }
                        for row in request.predictions
                    ],
                }
                for request in requests
            ],
        }
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _parse_response(raw_response: str, requests: tuple[DecisionRequest, ...]) -> dict[str, ProposedDecision]:
        payload = json.loads(raw_response)
        if not isinstance(payload, list):
            raise ValueError("response must be a JSON array")
        expected_symbols = {request.symbol for request in requests}
        decisions: dict[str, ProposedDecision] = {}
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("every decision must be an object")
            symbol = str(item["symbol"]).strip().upper().replace("/", "")
            if symbol not in expected_symbols or symbol in decisions:
                raise ValueError(f"unexpected or duplicate symbol {symbol!r}")
            action = DecisionAction(str(item["action"]).strip().lower())
            requested_usdt_amount = LLMDecisionPolicy._optional_float(item.get("requested_usdt_amount"))
            requested_quantity = LLMDecisionPolicy._optional_float(item.get("requested_quantity"))
            confidence = LLMDecisionPolicy._optional_float(item.get("confidence"))
            LLMDecisionPolicy._validate_action_fields(action, requested_usdt_amount, requested_quantity, confidence)
            decisions[symbol] = ProposedDecision(
                action=action,
                requested_usdt_amount=requested_usdt_amount,
                requested_quantity=requested_quantity,
                confidence=confidence,
                reason=str(item.get("reason", ""))[:1024],
            )
        missing = expected_symbols - decisions.keys()
        if missing:
            raise ValueError(f"missing decisions for symbols: {sorted(missing)}")
        return decisions

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return None if value is None else float(value)

    @staticmethod
    def _validate_action_fields(
        action: DecisionAction,
        requested_usdt_amount: float | None,
        requested_quantity: float | None,
        confidence: float | None,
    ) -> None:
        if confidence is None or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if requested_usdt_amount is not None and requested_usdt_amount <= 0:
            raise ValueError("requested_usdt_amount must be positive when provided")
        if requested_quantity is not None and requested_quantity <= 0:
            raise ValueError("requested_quantity must be positive when provided")
        if action == DecisionAction.BUY and (requested_usdt_amount is None or requested_quantity is not None):
            raise ValueError("buy requires requested_usdt_amount and null requested_quantity")
        if action == DecisionAction.SELL and (requested_quantity is None or requested_usdt_amount is not None):
            raise ValueError("sell requires requested_quantity and null requested_usdt_amount")
        if action == DecisionAction.HOLD and (requested_usdt_amount is not None or requested_quantity is not None):
            raise ValueError("hold requires null amounts")
