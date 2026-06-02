"""Orchestration for one auditable trading-agent dry-run cycle."""

from __future__ import annotations

from datetime import timedelta

from capm.domains.market_data import OHLCV
from capm.domains.trading import (
    AgentDecisionJournalEntry,
    DecisionRequest,
    PortfolioSnapshot,
    RiskConfig,
    normalize_trading_mode,
)
from capm.services.decision_policy import ThresholdDecisionPolicy
from capm.services.llm_decision_policy import LLMDecisionPolicy
from capm.services.risk_control import RiskControlService


class TradingAgentService:
    """Run one symbol decision cycle and persist the audit record."""

    def __init__(
        self,
        *,
        repository,
        decision_policy=None,
        risk_control=None,
    ) -> None:
        self._repository = repository
        self._decision_policy = decision_policy or ThresholdDecisionPolicy()
        self._risk_control = risk_control or RiskControlService()
        self.last_llm_batch = None

    def run_once(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str = "dry_run",
        portfolio: PortfolioSnapshot | None = None,
        risk_config: RiskConfig | None = None,
    ) -> AgentDecisionJournalEntry:
        """Run one dry-run decision cycle against the latest stored candle."""
        normalized_mode = normalize_trading_mode(mode)
        if normalized_mode != "dry_run":
            raise ValueError("Spot Demo execution adapter is not implemented yet; use dry-run mode.")
        latest_time = self._repository.get_latest_candle_time(symbol, interval)
        if latest_time is None:
            raise ValueError(f"No stored candle exists for {symbol} {interval}.")
        candle = self._repository.get_candle(symbol, interval, latest_time)
        if candle is None:
            raise ValueError(f"Latest stored candle for {symbol} {interval} could not be loaded.")
        resolved_config = risk_config or RiskConfig()
        predictions = self._repository.get_latest_prediction_journal_entries(
            symbol,
            interval,
            latest_time,
            timedelta(minutes=resolved_config.prediction_staleness_minutes),
        )
        request = DecisionRequest(
            cycle_id=f"{latest_time.isoformat()}:{symbol.upper()}:{interval}:{normalized_mode}:threshold",
            mode=normalized_mode,
            symbol=symbol,
            interval=interval,
            reference_time=latest_time,
            latest_candle=candle,
            predictions=predictions,
            portfolio=portfolio or PortfolioSnapshot(available_usdt=1000.0),
            risk_config=resolved_config,
        )
        decision = self._decision_policy.decide(request)
        risk_result = self._risk_control.evaluate(request, decision)
        return self._repository.save_agent_decision_journal_entry(
            self._journal_entry(request, decision, risk_result)
        )

    def run_llm_once(
        self,
        *,
        interval: str,
        llm_policy: LLMDecisionPolicy,
        mode: str = "dry_run",
        portfolio: PortfolioSnapshot | None = None,
        risk_config: RiskConfig | None = None,
    ) -> tuple[AgentDecisionJournalEntry, ...]:
        """Run one batched LLM call across all DB-available symbols."""
        normalized_mode = normalize_trading_mode(mode)
        if normalized_mode != "dry_run":
            raise ValueError("Spot Demo execution adapter is not implemented yet; use dry-run mode.")
        symbols = self._repository.get_available_symbols(interval)
        if not symbols:
            raise ValueError(f"No stored candles exist for interval {interval}.")
        resolved_portfolio = portfolio or PortfolioSnapshot(available_usdt=1000.0)
        resolved_config = risk_config or RiskConfig()
        requests = tuple(
            self._build_request(
                symbol=symbol,
                interval=interval,
                mode=normalized_mode,
                portfolio=resolved_portfolio,
                risk_config=resolved_config,
                policy_name="llm",
            )
            for symbol in symbols
        )
        batch = llm_policy.decide_batch(requests)
        self.last_llm_batch = batch
        entries = []
        for request in requests:
            decision = batch.decisions[request.symbol]
            risk_result = self._risk_control.evaluate(request, decision)
            entries.append(
                self._repository.save_agent_decision_journal_entry(
                    self._journal_entry(
                        request,
                        decision,
                        risk_result,
                        metadata={
                            "policy": "llm",
                            "llm_system_prompt": batch.system_prompt,
                            "llm_prompt": batch.prompt,
                            "llm_raw_response": batch.raw_response,
                            "llm_attempts": batch.attempts,
                        },
                    )
                )
            )
        return tuple(entries)

    def _build_request(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        portfolio: PortfolioSnapshot,
        risk_config: RiskConfig,
        policy_name: str,
    ) -> DecisionRequest:
        latest_time = self._repository.get_latest_candle_time(symbol, interval)
        if latest_time is None:
            raise ValueError(f"No stored candle exists for {symbol} {interval}.")
        candle = self._repository.get_candle(symbol, interval, latest_time)
        if candle is None:
            raise ValueError(f"Latest stored candle for {symbol} {interval} could not be loaded.")
        predictions = self._repository.get_latest_prediction_journal_entries(
            symbol,
            interval,
            latest_time,
            timedelta(minutes=risk_config.prediction_staleness_minutes),
        )
        return DecisionRequest(
            cycle_id=f"{latest_time.isoformat()}:{symbol.upper()}:{interval}:{mode}:{policy_name}",
            mode=mode,
            symbol=symbol,
            interval=interval,
            reference_time=latest_time,
            latest_candle=candle,
            predictions=predictions,
            portfolio=portfolio,
            risk_config=risk_config,
        )

    def _journal_entry(self, request, decision, risk_result, *, metadata=None) -> AgentDecisionJournalEntry:
        return AgentDecisionJournalEntry(
            cycle_id=request.cycle_id,
            mode=request.mode,
            symbol=request.symbol,
            interval=request.interval,
            reference_time=request.reference_time,
            action=decision.action.value,
            requested_quantity=decision.requested_quantity,
            requested_usdt_amount=decision.requested_usdt_amount,
            confidence=decision.confidence,
            reason=decision.reason,
            prediction_journal_ids=tuple(row.id for row in request.predictions if row.id is not None),
            prediction_snapshot={
                "predictions": [
                    {
                        "journal_id": row.id,
                        "model_name": row.model_name,
                        "predicted_return": row.predicted_return,
                        "predicted_direction": row.predicted_direction,
                    }
                    for row in request.predictions
                ]
            },
            market_snapshot=self._market_snapshot(request.latest_candle),
            portfolio_snapshot=request.portfolio.to_dict(),
            risk_status=risk_result.status,
            risk_violations=tuple(item.to_dict() for item in risk_result.violations),
            execution_status="not_submitted",
            metadata=metadata or {"policy": "threshold"},
        )

    @staticmethod
    def _market_snapshot(candle: OHLCV) -> dict[str, object]:
        return {
            "open_time": candle.open_time.isoformat(),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
        }
