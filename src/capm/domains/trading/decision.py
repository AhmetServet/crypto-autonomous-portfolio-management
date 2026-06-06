"""Domain entities for auditable trading-agent decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from capm.domains.market_data import OHLCV
from capm.domains.market_data.entities import ensure_utc, normalize_symbol
from capm.domains.prediction import PredictionJournalEntry


class DecisionAction(StrEnum):
    """Normalized trading actions."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


def normalize_trading_mode(value: str) -> str:
    """Normalize CLI-friendly mode names for persistence."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"dry_run", "spot_demo"}:
        raise ValueError(f"Unsupported trading mode {value!r}.")
    return normalized


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Portfolio state needed by the first trading-agent slice."""

    available_usdt: float
    base_asset_free: float = 0.0
    base_asset_locked: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "available_usdt": self.available_usdt,
            "base_asset_free": self.base_asset_free,
            "base_asset_locked": self.base_asset_locked,
        }


@dataclass(frozen=True, slots=True)
class RiskConfig:
    """Conservative hard limits for one trading cycle."""

    max_trade_usdt: float = 25.0
    max_position_usdt: float = 100.0
    min_predicted_return: float = 0.0005
    prediction_staleness_minutes: int = 5
    emergency_stop: bool = False
    max_daily_realized_loss_usdt: float = 50.0
    max_orders_per_day: int = 20
    order_cooldown_minutes: int = 5
    max_total_exposure_usdt: float = 100.0

    def __post_init__(self) -> None:
        if self.max_trade_usdt <= 0 or self.max_position_usdt <= 0:
            raise ValueError("trade and position limits must be positive.")
        if self.max_daily_realized_loss_usdt <= 0 or self.max_total_exposure_usdt <= 0:
            raise ValueError("operational USDT limits must be positive.")
        if self.max_orders_per_day < 1:
            raise ValueError("max_orders_per_day must be positive.")
        if self.order_cooldown_minutes < 0:
            raise ValueError("order_cooldown_minutes cannot be negative.")


@dataclass(frozen=True, slots=True)
class OperationalRiskSnapshot:
    """Persisted execution state required by unattended Spot Demo controls."""

    orders_today: int
    realized_pnl_today_usdt: float
    observed_at: datetime
    last_order_at: datetime | None = None
    position_quantity: float = 0.0
    position_cost_usdt: float = 0.0

    @property
    def average_entry_price(self) -> float | None:
        """Return average entry price for the remaining open position."""
        if self.position_quantity <= 0:
            return None
        return self.position_cost_usdt / self.position_quantity


@dataclass(frozen=True, slots=True)
class DecisionRequest:
    """Normalized input for one symbol decision."""

    cycle_id: str
    mode: str
    symbol: str
    interval: str
    reference_time: datetime
    latest_candle: OHLCV
    recent_candles: tuple[OHLCV, ...]
    indicators: dict[str, str | None]
    predictions: tuple[PredictionJournalEntry, ...]
    portfolio: PortfolioSnapshot
    risk_config: RiskConfig

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", normalize_trading_mode(self.mode))
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))


@dataclass(frozen=True, slots=True)
class ProposedDecision:
    """Policy output before hard risk validation."""

    action: DecisionAction
    requested_usdt_amount: float | None = None
    requested_quantity: float | None = None
    confidence: float | None = None
    reason: str = ""


@dataclass(frozen=True, slots=True)
class AgentDecisionJournalEntry:
    """Durable audit record for one symbol decision."""

    cycle_id: str
    mode: str
    symbol: str
    interval: str
    reference_time: datetime
    action: str
    risk_status: str
    execution_status: str
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    requested_quantity: float | None = None
    requested_usdt_amount: float | None = None
    confidence: float | None = None
    reason: str = ""
    prediction_journal_ids: tuple[int, ...] = ()
    prediction_snapshot: dict[str, Any] = field(default_factory=dict)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    portfolio_snapshot: dict[str, Any] = field(default_factory=dict)
    risk_violations: tuple[dict[str, Any], ...] = ()
    exchange_order_id: str | None = None
    exchange_client_order_id: str | None = None
    exchange_response: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", normalize_trading_mode(self.mode))
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "action", DecisionAction(self.action).value)
        object.__setattr__(self, "reference_time", ensure_utc(self.reference_time))


@dataclass(frozen=True, slots=True)
class AgentDecisionJournalSummary:
    """Aggregate decision counts for one time range."""

    symbol: str
    interval: str
    start_time: datetime
    end_time: datetime
    decision_count: int
    action_counts: dict[str, int]
    risk_status_counts: dict[str, int]
    execution_status_counts: dict[str, int]
    mode_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "decision_count": self.decision_count,
            "action_counts": self.action_counts,
            "risk_status_counts": self.risk_status_counts,
            "execution_status_counts": self.execution_status_counts,
            "mode_counts": self.mode_counts,
        }
