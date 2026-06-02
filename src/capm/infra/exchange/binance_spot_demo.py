"""Authenticated Binance Spot Demo trading adapter."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from capm.core.config import BinanceSettings
from capm.core.errors import ConfigurationError, ExchangeAPIError
from capm.domains.market_data import normalize_symbol
from capm.domains.trading import PortfolioSnapshot, ProposedDecision


@dataclass(slots=True)
class BinanceSpotDemoTradingAdapter:
    """Submit authenticated spot orders only against Binance Spot Demo Mode."""

    settings: BinanceSettings
    client: httpx.Client | None = None
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    _owns_client: bool = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.settings.mode != "demo":
            raise ConfigurationError("Spot Demo trading requires CAPM_BINANCE_MODE=demo.")
        if self.settings.spot_rest_base_url.rstrip("/") != "https://demo-api.binance.com":
            raise ConfigurationError("Spot Demo trading refuses non-demo Binance REST base URLs.")
        if not self.settings.api_key or not self.settings.api_secret:
            raise ConfigurationError("Spot Demo trading requires CAPM_BINANCE_API_KEY and CAPM_BINANCE_API_SECRET.")
        self._owns_client = self.client is None
        if self.client is None:
            self.client = httpx.Client(
                base_url=self.settings.spot_rest_base_url,
                timeout=self.settings.request_timeout_seconds,
                trust_env=self.settings.trust_env,
            )

    def close(self) -> None:
        if self._owns_client and self.client is not None:
            self.client.close()

    def get_portfolio(self, symbol: str) -> PortfolioSnapshot:
        """Read USDT and base-asset balances for one USDT pair."""
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol.endswith("USDT"):
            raise ValueError("Initial Spot Demo adapter supports USDT quote pairs only.")
        balances = {
            str(item["asset"]): item
            for item in self._signed_request("GET", "/api/v3/account").get("balances", [])
        }
        base_asset = normalized_symbol.removesuffix("USDT")
        usdt = balances.get("USDT", {})
        base = balances.get(base_asset, {})
        return PortfolioSnapshot(
            available_usdt=float(usdt.get("free", 0)),
            base_asset_free=float(base.get("free", 0)),
            base_asset_locked=float(base.get("locked", 0)),
        )

    def submit_market_order(self, symbol: str, decision: ProposedDecision) -> dict[str, Any]:
        """Submit one approved market buy or sell."""
        params: dict[str, Any] = {
            "symbol": normalize_symbol(symbol),
            "side": decision.action.value.upper(),
            "type": "MARKET",
        }
        if decision.action.value == "buy":
            params["quoteOrderQty"] = decision.requested_usdt_amount
        elif decision.action.value == "sell":
            params["quantity"] = decision.requested_quantity
        else:
            raise ValueError("Hold decisions cannot be submitted to Binance.")
        return self._signed_request("POST", "/api/v3/order", params=params)

    def _signed_request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.client is not None
        payload = dict(params or {})
        payload["timestamp"] = self.now_ms()
        query = urlencode(payload)
        payload["signature"] = hmac.new(
            self.settings.api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()
        response = self.client.request(
            method,
            path,
            params=payload,
            headers={"X-MBX-APIKEY": self.settings.api_key},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExchangeAPIError(f"Binance Spot Demo request failed: {response.text}") from exc
        result = response.json()
        if not isinstance(result, dict):
            raise ExchangeAPIError("Expected Binance Spot Demo response object.")
        return result
