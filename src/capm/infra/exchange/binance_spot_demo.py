"""Authenticated Binance Spot Demo trading adapter."""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from capm.core.config import BinanceSettings
from capm.core.errors import ConfigurationError, ExchangeAPIError, ValidationError
from capm.domains.market_data import normalize_symbol
from capm.domains.trading import PortfolioSnapshot, ProposedDecision


@dataclass(frozen=True, slots=True)
class BinanceSymbolRules:
    """Exchange constraints required before submitting a spot market order."""

    symbol: str
    status: str
    quote_order_qty_market_allowed: bool
    min_quantity: Decimal
    max_quantity: Decimal
    step_size: Decimal
    min_notional: Decimal


@dataclass(slots=True)
class BinanceSpotDemoTradingAdapter:
    """Submit authenticated spot orders only against Binance Spot Demo Mode."""

    settings: BinanceSettings
    client: httpx.Client | None = None
    now_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    _owns_client: bool = field(init=False, repr=False)
    _symbol_rules: dict[str, BinanceSymbolRules] = field(init=False, repr=False, default_factory=dict)

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
        rules = self.get_symbol_rules(symbol)
        params: dict[str, Any] = {
            "symbol": rules.symbol,
            "side": decision.action.value.upper(),
            "type": "MARKET",
        }
        if decision.action.value == "buy":
            if not rules.quote_order_qty_market_allowed:
                raise ValidationError(f"{rules.symbol} does not allow market buys by quote amount.")
            quote_amount = self._positive_decimal(decision.requested_usdt_amount, "requested_usdt_amount")
            if quote_amount < rules.min_notional:
                raise ValidationError(
                    f"{rules.symbol} market buy quote amount {quote_amount} is below minimum notional "
                    f"{rules.min_notional}."
                )
            params["quoteOrderQty"] = self._decimal_param(quote_amount)
        elif decision.action.value == "sell":
            quantity = self._positive_decimal(decision.requested_quantity, "requested_quantity")
            quantity = self._floor_to_step(quantity, rules.step_size)
            if quantity < rules.min_quantity:
                raise ValidationError(
                    f"{rules.symbol} normalized market sell quantity {quantity} is below minimum "
                    f"quantity {rules.min_quantity}."
                )
            if quantity > rules.max_quantity:
                raise ValidationError(
                    f"{rules.symbol} normalized market sell quantity {quantity} exceeds maximum "
                    f"quantity {rules.max_quantity}."
                )
            params["quantity"] = self._decimal_param(quantity)
        else:
            raise ValueError("Hold decisions cannot be submitted to Binance.")
        return self._signed_request("POST", "/api/v3/order", params=params)

    def get_order(self, symbol: str, order_id: str | int) -> dict[str, Any]:
        """Read the latest exchange state for one submitted order."""
        return self._signed_request(
            "GET",
            "/api/v3/order",
            params={"symbol": normalize_symbol(symbol), "orderId": str(order_id)},
        )

    def get_symbol_rules(self, symbol: str) -> BinanceSymbolRules:
        """Load and cache Binance filters used for market-order validation."""
        normalized_symbol = normalize_symbol(symbol)
        if normalized_symbol in self._symbol_rules:
            return self._symbol_rules[normalized_symbol]
        payload = self._public_request("GET", "/api/v3/exchangeInfo", params={"symbol": normalized_symbol})
        symbols = payload.get("symbols", [])
        if not isinstance(symbols, list) or len(symbols) != 1:
            raise ExchangeAPIError(f"Expected exchange rules for exactly one symbol: {normalized_symbol}.")
        symbol_payload = symbols[0]
        filters = {
            item["filterType"]: item
            for item in symbol_payload.get("filters", [])
            if isinstance(item, dict) and "filterType" in item
        }
        lot_size = filters.get("MARKET_LOT_SIZE") or filters.get("LOT_SIZE")
        notional = filters.get("NOTIONAL") or filters.get("MIN_NOTIONAL")
        if lot_size is None or notional is None:
            raise ExchangeAPIError(f"Missing market-order filters for {normalized_symbol}.")
        rules = BinanceSymbolRules(
            symbol=normalized_symbol,
            status=str(symbol_payload.get("status", "")),
            quote_order_qty_market_allowed=bool(symbol_payload.get("quoteOrderQtyMarketAllowed", False)),
            min_quantity=Decimal(str(lot_size["minQty"])),
            max_quantity=Decimal(str(lot_size["maxQty"])),
            step_size=Decimal(str(lot_size["stepSize"])),
            min_notional=Decimal(str(notional.get("minNotional", "0"))),
        )
        if rules.status != "TRADING":
            raise ValidationError(f"{normalized_symbol} is not available for trading: status={rules.status!r}.")
        self._symbol_rules[normalized_symbol] = rules
        return rules

    def _public_request(self, method: str, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        assert self.client is not None
        response = self.client.request(method, path, params=params)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExchangeAPIError(f"Binance Spot Demo request failed: {response.text}") from exc
        result = response.json()
        if not isinstance(result, dict):
            raise ExchangeAPIError("Expected Binance Spot Demo response object.")
        return result

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

    @staticmethod
    def _positive_decimal(value: float | None, field_name: str) -> Decimal:
        if value is None:
            raise ValidationError(f"{field_name} is required.")
        decimal_value = Decimal(str(value))
        if decimal_value <= 0:
            raise ValidationError(f"{field_name} must be greater than zero.")
        return decimal_value

    @staticmethod
    def _floor_to_step(value: Decimal, step_size: Decimal) -> Decimal:
        if step_size <= 0:
            raise ExchangeAPIError("Binance symbol step size must be greater than zero.")
        return (value / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size

    @staticmethod
    def _decimal_param(value: Decimal) -> str:
        return format(value, "f")
