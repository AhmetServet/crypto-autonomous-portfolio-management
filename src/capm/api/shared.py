"""Shared helpers for dashboard API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from capm.domains.market_data import interval_to_timedelta

from .schemas import AgentRunOnceRequest, LiveCycleRunOnceRequest


def risk_args_from_request(request: AgentRunOnceRequest | LiveCycleRunOnceRequest) -> SimpleNamespace:
    """Normalize risk-related request fields into a CLI-compatible namespace."""
    return SimpleNamespace(
        max_trade_usdt=request.max_trade_usdt,
        max_position_usdt=request.max_position_usdt,
        min_predicted_return=getattr(request, "min_predicted_return", 0.0005),
        prediction_staleness_minutes=getattr(request, "prediction_staleness_minutes", 5),
        emergency_stop=request.emergency_stop,
        max_daily_realized_loss_usdt=request.max_daily_realized_loss_usdt,
        max_orders_per_day=request.max_orders_per_day,
        order_cooldown_minutes=request.order_cooldown_minutes,
        max_total_exposure_usdt=request.max_total_exposure_usdt,
    )


def datetime_now_minus_interval(interval: str) -> datetime:
    """Return the default settlement cutoff used by the CLI."""
    return datetime.now(UTC) - interval_to_timedelta(interval)


def time_range_payload(item: object) -> dict[str, object]:
    """Serialize a simple coverage gap range object."""
    return {
        "start": item.start_time,
        "end": item.end_time,
    }


def coverage_range_payload(item: object) -> dict[str, object]:
    """Serialize a repository coverage range object."""
    return {
        "coinpair_id": item.coinpair_id,
        "table_name": item.table_name,
        "symbol": item.symbol,
        "interval": item.interval,
        "start": item.start_open_time,
        "end": item.end_open_time,
    }
