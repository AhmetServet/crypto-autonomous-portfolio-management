"""Hard risk controls for trading-agent decisions."""

from __future__ import annotations

from datetime import timedelta

from capm.domains.trading import (
    DecisionAction,
    DecisionRequest,
    OperationalRiskSnapshot,
    ProposedDecision,
    RiskResult,
    RiskViolation,
)


class RiskControlService:
    """Reject unsafe decisions before any exchange adapter is called."""

    def evaluate(self, request: DecisionRequest, decision: ProposedDecision) -> RiskResult:
        """Evaluate hard limits for one proposed action."""
        if decision.action == DecisionAction.HOLD:
            return RiskResult(status="skipped")

        violations: list[RiskViolation] = []
        if decision.action == DecisionAction.BUY:
            requested = decision.requested_usdt_amount or 0.0
            if requested <= 0:
                violations.append(RiskViolation("invalid_trade_size", "buy amount must be greater than zero"))
            if requested > request.risk_config.max_trade_usdt:
                violations.append(
                    RiskViolation(
                        "max_trade_size",
                        "requested buy amount exceeds configured maximum",
                        {"requested_usdt_amount": requested, "max_trade_usdt": request.risk_config.max_trade_usdt},
                    )
                )
            if requested > request.portfolio.available_usdt:
                violations.append(
                    RiskViolation(
                        "insufficient_usdt",
                        "requested buy amount exceeds available USDT",
                        {"requested_usdt_amount": requested, "available_usdt": request.portfolio.available_usdt},
                    )
                )
            current_position_value = request.portfolio.base_asset_free * float(request.latest_candle.close)
            if current_position_value + requested > request.risk_config.max_position_usdt:
                violations.append(
                    RiskViolation(
                        "max_position_size",
                        "buy would exceed configured position cap",
                        {
                            "current_position_usdt": current_position_value,
                            "requested_usdt_amount": requested,
                            "max_position_usdt": request.risk_config.max_position_usdt,
                        },
                    )
                )
        elif decision.action == DecisionAction.SELL:
            requested = decision.requested_quantity or 0.0
            if requested <= 0 or request.portfolio.base_asset_free <= 0:
                violations.append(RiskViolation("zero_balance_sell", "sell requested without available base asset"))
            elif requested > request.portfolio.base_asset_free:
                violations.append(
                    RiskViolation(
                        "insufficient_base_asset",
                        "requested sell quantity exceeds available base asset",
                        {"requested_quantity": requested, "base_asset_free": request.portfolio.base_asset_free},
                    )
                )

        return RiskResult(status="rejected" if violations else "approved", violations=tuple(violations))

    def evaluate_operational(
        self,
        request: DecisionRequest,
        decision: ProposedDecision,
        snapshot: OperationalRiskSnapshot,
    ) -> RiskResult:
        """Evaluate persistent controls required before unattended execution."""
        if decision.action == DecisionAction.HOLD:
            return RiskResult(status="skipped")

        config = request.risk_config
        violations: list[RiskViolation] = []
        if config.emergency_stop:
            violations.append(RiskViolation("emergency_stop", "Spot Demo execution is disabled by emergency stop"))
        if snapshot.realized_pnl_today_usdt <= -config.max_daily_realized_loss_usdt:
            violations.append(
                RiskViolation(
                    "max_daily_realized_loss",
                    "daily realized loss limit has been reached",
                    {
                        "realized_pnl_today_usdt": snapshot.realized_pnl_today_usdt,
                        "max_daily_realized_loss_usdt": config.max_daily_realized_loss_usdt,
                    },
                )
            )
        if snapshot.orders_today >= config.max_orders_per_day:
            violations.append(
                RiskViolation(
                    "max_orders_per_day",
                    "daily submitted-order limit has been reached",
                    {"orders_today": snapshot.orders_today, "max_orders_per_day": config.max_orders_per_day},
                )
            )
        if snapshot.last_order_at is not None:
            next_allowed = snapshot.last_order_at + timedelta(minutes=config.order_cooldown_minutes)
            if snapshot.observed_at < next_allowed:
                violations.append(
                    RiskViolation(
                        "order_cooldown",
                        "minimum interval between orders has not elapsed",
                        {
                            "last_order_at": snapshot.last_order_at.isoformat(),
                            "next_allowed_at": next_allowed.isoformat(),
                        },
                    )
                )
        current_exposure = request.portfolio.base_asset_free * float(request.latest_candle.close)
        requested_exposure = (decision.requested_usdt_amount or 0.0) if decision.action == DecisionAction.BUY else 0.0
        if current_exposure + requested_exposure > config.max_total_exposure_usdt:
            violations.append(
                RiskViolation(
                    "max_total_exposure",
                    "order would exceed configured priced exposure limit",
                    {
                        "current_exposure_usdt": current_exposure,
                        "requested_exposure_usdt": requested_exposure,
                        "max_total_exposure_usdt": config.max_total_exposure_usdt,
                    },
                )
            )
        return RiskResult(status="rejected" if violations else "approved", violations=tuple(violations))
