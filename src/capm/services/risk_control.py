"""Hard risk controls for trading-agent decisions."""

from __future__ import annotations

from capm.domains.trading import DecisionAction, DecisionRequest, ProposedDecision, RiskResult, RiskViolation


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
