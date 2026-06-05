"""Unit tests for persistent Spot Demo operational risk controls."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from capm.domains.market_data import OHLCV
from capm.domains.trading import (
    DecisionAction,
    DecisionRequest,
    OperationalRiskSnapshot,
    PortfolioSnapshot,
    ProposedDecision,
    RiskConfig,
)
from capm.services.risk_control import RiskControlService


def _request(config: RiskConfig | None = None, *, base_asset_free: float = 0.0) -> DecisionRequest:
    reference_time = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)
    candle = OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=reference_time,
        close_time=reference_time + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
        quote_asset_volume=Decimal("100"),
        trade_count=1,
        taker_buy_base_asset_volume=Decimal("1"),
        taker_buy_quote_asset_volume=Decimal("100"),
    )
    return DecisionRequest(
        cycle_id="cycle",
        mode="spot-demo",
        symbol="BTCUSDT",
        interval="1m",
        reference_time=reference_time,
        latest_candle=candle,
        recent_candles=(candle,),
        indicators={},
        predictions=(),
        portfolio=PortfolioSnapshot(available_usdt=1000, base_asset_free=base_asset_free),
        risk_config=config or RiskConfig(),
    )


class OperationalRiskTests(unittest.TestCase):
    def test_config_rejects_invalid_operational_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_orders_per_day"):
            RiskConfig(max_orders_per_day=0)

    def test_rejects_daily_loss_order_count_and_cooldown(self) -> None:
        request = _request(
            RiskConfig(
                max_daily_realized_loss_usdt=10,
                max_orders_per_day=2,
                order_cooldown_minutes=5,
            )
        )
        snapshot = OperationalRiskSnapshot(
            orders_today=2,
            realized_pnl_today_usdt=-10,
            observed_at=request.reference_time,
            last_order_at=request.reference_time - timedelta(minutes=1),
        )

        result = RiskControlService().evaluate_operational(
            request,
            ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=5),
            snapshot,
        )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(
            {violation.rule for violation in result.violations},
            {"max_daily_realized_loss", "max_orders_per_day", "order_cooldown"},
        )

    def test_rejects_priced_exposure_limit(self) -> None:
        request = _request(
            replace(RiskConfig(), max_total_exposure_usdt=100),
            base_asset_free=0.95,
        )

        result = RiskControlService().evaluate_operational(
            request,
            ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=10),
            OperationalRiskSnapshot(orders_today=0, realized_pnl_today_usdt=0, observed_at=request.reference_time),
        )

        self.assertEqual(result.status, "rejected")
        self.assertEqual(result.violations[0].rule, "max_total_exposure")


if __name__ == "__main__":
    unittest.main()
