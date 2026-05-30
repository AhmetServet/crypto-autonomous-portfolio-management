"""Deterministic baseline decision policy for the first trading-agent slice."""

from __future__ import annotations

from capm.domains.trading import DecisionAction, DecisionRequest, ProposedDecision


class ThresholdDecisionPolicy:
    """Convert the strongest recent prediction into a conservative action."""

    def decide(self, request: DecisionRequest) -> ProposedDecision:
        """Return one proposed action without bypassing later risk checks."""
        if not request.predictions:
            return ProposedDecision(action=DecisionAction.HOLD, reason="no usable prediction")

        prediction = max(request.predictions, key=lambda row: abs(row.predicted_return))
        confidence = abs(prediction.predicted_return)
        if confidence < request.risk_config.min_predicted_return:
            return ProposedDecision(
                action=DecisionAction.HOLD,
                confidence=confidence,
                reason="strongest predicted return is below threshold",
            )
        if prediction.predicted_direction == "up":
            return ProposedDecision(
                action=DecisionAction.BUY,
                requested_usdt_amount=request.risk_config.max_trade_usdt,
                confidence=confidence,
                reason=f"{prediction.model_name} predicted up above threshold",
            )
        if prediction.predicted_direction == "down" and request.portfolio.base_asset_free > 0:
            return ProposedDecision(
                action=DecisionAction.SELL,
                requested_quantity=request.portfolio.base_asset_free,
                confidence=confidence,
                reason=f"{prediction.model_name} predicted down above threshold",
            )
        return ProposedDecision(
            action=DecisionAction.HOLD,
            confidence=confidence,
            reason="down prediction has no available base asset to sell",
        )
