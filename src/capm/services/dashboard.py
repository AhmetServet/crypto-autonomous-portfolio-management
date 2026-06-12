"""Read-only dashboard payloads for agent observability surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import os
from typing import Any, Protocol

from capm.core.config import BinanceSettings
from capm.domains.market_data import interval_to_timedelta
from capm.domains.trading import AgentDecisionJournalEntry, OperationalRiskSnapshot, RiskConfig
from capm.infra.exchange import BinanceSpotDemoTradingAdapter
from capm.services.prediction_journal import PredictionJournalService


class DashboardRepositoryPort(Protocol):
    """Database reads required by the dashboard service."""

    def get_available_symbols(self, interval: str) -> tuple[str, ...]:
        """Return symbols with stored candles for the interval."""

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Return the latest stored candle timestamp."""

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> Any | None:
        """Return one stored candle."""

    def get_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> list[Any]:
        """Return stored candles for a range."""

    def get_latest_indicator_time(self, symbol: str, interval: str) -> datetime | None:
        """Return the latest stored indicator timestamp."""

    def get_indicator_set(self, symbol: str, interval: str, open_time: datetime) -> Any | None:
        """Return one stored indicator set."""

    def get_indicator_batch(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> list[Any]:
        """Return stored indicator rows for a range."""

    def list_recent_prediction_journal_entries(self, symbol: str, interval: str, limit: int = 20) -> tuple[Any, ...]:
        """Return recent prediction rows."""

    def list_recent_agent_decision_journal_entries(
        self,
        symbol: str,
        interval: str,
        limit: int = 20,
    ) -> tuple[AgentDecisionJournalEntry, ...]:
        """Return recent agent decision rows."""

    def summarize_prediction_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        model_name: str | None = None,
    ) -> Any:
        """Return aggregate prediction metrics."""

    def summarize_agent_decision_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> Any:
        """Return aggregate decision metrics."""

    def get_operational_risk_snapshot(self, symbol: str, at: datetime) -> OperationalRiskSnapshot:
        """Return operational risk state for one symbol."""

    def get_agent_decision_journal_entry(self, journal_id: int) -> AgentDecisionJournalEntry | None:
        """Return one agent decision journal row by id."""


@dataclass(frozen=True, slots=True)
class DashboardReportRequest:
    """Read parameters for one dashboard report."""

    symbol: str
    interval: str = "1m"
    limit: int = 20
    lookback_hours: int = 24
    include_prompts: bool = False
    include_spot_demo: bool = False


def prediction_report_payload(entry: Any) -> dict[str, object]:
    """Build a compact representation for one prediction journal row."""
    return {
        "id": entry.id,
        "model_name": entry.model_name,
        "artifact_kind": entry.artifact_kind,
        "artifact_path": entry.artifact_path,
        "reference_time": entry.reference_time,
        "prediction_time": entry.prediction_time,
        "forecast_horizon": entry.forecast_horizon,
        "target_mode": entry.target_mode,
        "reference_value": entry.reference_value,
        "predicted_value": entry.predicted_value,
        "predicted_return": entry.predicted_return,
        "predicted_direction": entry.predicted_direction,
        "actual_return": entry.actual_return,
        "actual_direction": entry.actual_direction,
        "direction_correct": entry.direction_correct,
        "settled_at": entry.settled_at,
    }


def decision_report_payload(entry: AgentDecisionJournalEntry, *, include_prompts: bool = False) -> dict[str, object]:
    """Build a compact representation for one agent decision row."""
    metadata = dict(entry.metadata)
    return {
        "id": entry.id,
        "cycle_id": entry.cycle_id,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "mode": entry.mode,
        "symbol": entry.symbol,
        "interval": entry.interval,
        "reference_time": entry.reference_time,
        "action": entry.action,
        "requested_quantity": entry.requested_quantity,
        "requested_usdt_amount": entry.requested_usdt_amount,
        "confidence": entry.confidence,
        "reason": entry.reason,
        "prediction_journal_ids": entry.prediction_journal_ids,
        "risk_status": entry.risk_status,
        "risk_violations": entry.risk_violations,
        "execution_status": entry.execution_status,
        "exchange_order_id": entry.exchange_order_id,
        "exchange_client_order_id": entry.exchange_client_order_id,
        "llm": {
            "model": metadata.get("llm_model"),
            "provider_host": metadata.get("llm_provider_host"),
            "latency_seconds": metadata.get("llm_latency_seconds"),
            "attempts": metadata.get("llm_attempts"),
            "usage": metadata.get("llm_usage"),
            "raw_response": metadata.get("llm_raw_response") if include_prompts else None,
            "system_prompt": metadata.get("llm_system_prompt") if include_prompts else None,
            "prompt": metadata.get("llm_prompt") if include_prompts else None,
        },
        "exchange_response": entry.exchange_response,
    }


class DashboardReportService:
    """Builds read-only dashboard payloads from repository state."""

    def __init__(self, repository: DashboardRepositoryPort) -> None:
        self.repository = repository

    def list_symbols(self, *, interval: str) -> dict[str, object]:
        """Return symbols currently available in the local database."""
        now = datetime.now(UTC)
        symbols = self.repository.get_available_symbols(interval)
        return {
            "status": "ok",
            "interval": interval,
            "symbols": symbols,
            "symbol_statuses": [
                self._symbol_status_payload(symbol=symbol, interval=interval, now=now)
                for symbol in symbols
            ],
        }

    def health(self) -> dict[str, object]:
        """Return API and database reachability."""
        now = datetime.now(UTC)
        try:
            symbols = self.repository.get_available_symbols("1m")
        except Exception as exc:  # pragma: no cover - defensive boundary
            return {"status": "error", "database": "unreachable", "error": str(exc)}
        return {
            "status": "ok",
            "api": "reachable",
            "database": "reachable",
            "available_symbols_1m": symbols,
            "symbol_statuses_1m": [
                self._symbol_status_payload(symbol=symbol, interval="1m", now=now)
                for symbol in symbols
            ],
            "binance_demo": self._binance_demo_health_payload(),
            "llm_provider": self._llm_provider_health_payload(),
        }

    def summary(self, request: DashboardReportRequest) -> dict[str, object]:
        """Build the full dashboard summary payload."""
        return self._report_payload(request)

    def predictions(self, *, symbol: str, interval: str, limit: int) -> dict[str, object]:
        """Return recent prediction journal rows."""
        entries = self.repository.list_recent_prediction_journal_entries(symbol, interval, limit)
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "predictions": [prediction_report_payload(entry) for entry in entries],
        }

    def charts(self, *, symbol: str, interval: str, lookback_hours: int, limit: int) -> dict[str, object]:
        """Return chart-ready market, prediction, decision, and PnL series."""
        now = datetime.now(UTC)
        latest_candle_time = self.repository.get_latest_candle_time(symbol, interval)
        end_time = latest_candle_time + interval_to_timedelta(interval) if latest_candle_time else now
        start_time = end_time - timedelta(hours=lookback_hours)
        candles = self.repository.get_candles(symbol, interval, start_time, end_time)
        if limit > 0 and len(candles) > limit:
            step = max(1, len(candles) // limit)
            candles = candles[::step][-limit:]
        indicators_by_time = {
            item.open_time: item
            for item in self.repository.get_indicator_batch(symbol, interval, start_time, end_time)
        }
        predictions = self.repository.list_recent_prediction_journal_entries(symbol, interval, limit)
        decisions = self.repository.list_recent_agent_decision_journal_entries(symbol, interval, limit)
        order_rows = self._order_rows(tuple(decisions))
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "lookback_hours": lookback_hours,
            "candles": [
                self._chart_candle_payload(candle, indicators_by_time.get(candle.open_time))
                for candle in candles
            ],
            "prediction_markers": [
                prediction_report_payload(entry)
                for entry in predictions
                if start_time <= entry.reference_time < end_time
            ],
            "decision_markers": [
                decision_report_payload(entry)
                for entry in decisions
                if start_time <= entry.reference_time < end_time
            ],
            "pnl_curve": self._pnl_curve(order_rows),
        }

    def decisions(self, *, symbol: str, interval: str, limit: int, include_prompts: bool = False) -> dict[str, object]:
        """Return recent agent decision rows."""
        entries = self.repository.list_recent_agent_decision_journal_entries(symbol, interval, limit)
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "decisions": [
                decision_report_payload(entry, include_prompts=include_prompts) for entry in entries
            ],
        }

    def orders(self, *, symbol: str, interval: str, limit: int) -> dict[str, object]:
        """Return recent submitted Spot Demo orders with derived PnL."""
        entries = self.repository.list_recent_agent_decision_journal_entries(symbol, interval, max(limit * 5, limit))
        order_rows = self._order_rows(entries)
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "orders": order_rows[:limit],
        }

    def position(self, *, symbol: str, interval: str) -> dict[str, object]:
        """Return current derived position state."""
        now = datetime.now(UTC)
        latest_close = self._latest_close(symbol, interval)
        operational_snapshot = self.repository.get_operational_risk_snapshot(symbol, now)
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "position": self._position_payload(operational_snapshot, latest_close),
        }

    def risk(self, *, symbol: str) -> dict[str, object]:
        """Return operational risk state."""
        now = datetime.now(UTC)
        operational_snapshot = self.repository.get_operational_risk_snapshot(symbol, now)
        return {
            "status": "ok",
            "symbol": symbol,
            "operational_risk": self._operational_risk_payload(operational_snapshot, now),
        }

    def prompt(self, *, journal_id: int) -> dict[str, object]:
        """Return prompt details for one LLM-backed decision."""
        entry = self.repository.get_agent_decision_journal_entry(journal_id)
        if entry is None:
            return {"status": "not_found", "journal_id": journal_id}
        metadata = dict(entry.metadata)
        return {
            "status": "ok",
            "journal_id": journal_id,
            "symbol": entry.symbol,
            "interval": entry.interval,
            "model": metadata.get("llm_model"),
            "provider_host": metadata.get("llm_provider_host"),
            "latency_seconds": metadata.get("llm_latency_seconds"),
            "attempts": metadata.get("llm_attempts"),
            "usage": metadata.get("llm_usage"),
            "system_prompt": metadata.get("llm_system_prompt"),
            "prompt": metadata.get("llm_prompt"),
            "raw_response": metadata.get("llm_raw_response"),
        }

    def _report_payload(self, request: DashboardReportRequest) -> dict[str, object]:
        now = datetime.now(UTC)
        latest_candle_time = self.repository.get_latest_candle_time(request.symbol, request.interval)
        latest_candle = None
        if latest_candle_time is not None:
            latest_candle = self.repository.get_candle(request.symbol, request.interval, latest_candle_time)
        latest_indicator_time = self.repository.get_latest_indicator_time(request.symbol, request.interval)
        latest_indicator = None
        if latest_indicator_time is not None:
            latest_indicator = self.repository.get_indicator_set(request.symbol, request.interval, latest_indicator_time)

        summary_start = now - timedelta(hours=request.lookback_hours)
        predictions = self.repository.list_recent_prediction_journal_entries(request.symbol, request.interval, request.limit)
        decisions = self.repository.list_recent_agent_decision_journal_entries(request.symbol, request.interval, request.limit)
        prediction_summary = PredictionJournalService(
            journal_repository=self.repository,
            market_data_repository=self.repository,
        ).summarize(
            symbol=request.symbol,
            interval=request.interval,
            start_time=summary_start,
            end_time=now,
        )
        decision_summary = self.repository.summarize_agent_decision_journal(
            symbol=request.symbol,
            interval=request.interval,
            start_time=summary_start,
            end_time=now,
        )
        operational_snapshot = self.repository.get_operational_risk_snapshot(request.symbol, now)
        latest_close = float(latest_candle.close) if latest_candle else None

        portfolio = None
        if request.include_spot_demo:
            adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
            try:
                portfolio = adapter.get_portfolio(request.symbol).to_dict()
            finally:
                adapter.close()

        return {
            "status": "ok",
            "generated_at": now,
            "symbol": request.symbol,
            "interval": request.interval,
            "lookback_hours": request.lookback_hours,
            "market": {
                "latest_candle_time": latest_candle_time,
                "latest_candle_age_seconds": self._age_seconds(latest_candle_time, now),
                "latest_candle": latest_candle.to_dict() if latest_candle else None,
                "latest_indicator_time": latest_indicator_time,
                "latest_indicator_age_seconds": self._age_seconds(latest_indicator_time, now),
                "indicator_ready": latest_indicator.is_ready if latest_indicator else None,
                "missing_indicator_outputs": latest_indicator.missing_outputs if latest_indicator else (),
                "indicators": latest_indicator.values if latest_indicator else {},
            },
            "spot_demo_portfolio": portfolio,
            "operational_risk": self._operational_risk_payload(operational_snapshot, now),
            "position": self._position_payload(operational_snapshot, latest_close),
            "prediction_summary": prediction_summary.to_dict(),
            "decision_summary": decision_summary.to_dict(),
            "recent_predictions": [prediction_report_payload(entry) for entry in predictions],
            "recent_decisions": [
                decision_report_payload(entry, include_prompts=request.include_prompts) for entry in decisions
            ],
        }

    def _symbol_status_payload(self, *, symbol: str, interval: str, now: datetime) -> dict[str, object]:
        latest_candle_time = self.repository.get_latest_candle_time(symbol, interval)
        latest_indicator_time = self.repository.get_latest_indicator_time(symbol, interval)
        indicator = (
            self.repository.get_indicator_set(symbol, interval, latest_indicator_time)
            if latest_indicator_time is not None
            else None
        )
        return {
            "symbol": symbol,
            "interval": interval,
            "latest_candle_time": latest_candle_time,
            "latest_candle_age_seconds": self._age_seconds(latest_candle_time, now),
            "latest_indicator_time": latest_indicator_time,
            "latest_indicator_age_seconds": self._age_seconds(latest_indicator_time, now),
            "indicator_ready": indicator.is_ready if indicator else None,
            "missing_indicator_outputs": indicator.missing_outputs if indicator else (),
        }

    @staticmethod
    def _binance_demo_health_payload() -> dict[str, object]:
        try:
            settings = BinanceSettings.from_env(mode="demo")
        except Exception as exc:
            return {"status": "error", "mode": "demo", "error": str(exc)}
        return {
            "status": "configured" if settings.api_key and settings.api_secret else "missing_credentials",
            "mode": settings.mode,
            "base_url": settings.spot_rest_base_url,
            "api_key_configured": bool(settings.api_key),
            "api_secret_configured": bool(settings.api_secret),
        }

    @staticmethod
    def _llm_provider_health_payload() -> dict[str, object]:
        api_key = os.getenv("CAPM_LLM_API_KEY", "").strip()
        model = os.getenv("CAPM_LLM_MODEL", "").strip()
        base_url = os.getenv("CAPM_LLM_BASE_URL", "").strip() or "https://openrouter.ai/api/v1"
        return {
            "status": "configured" if api_key and model and base_url else "missing_configuration",
            "base_url": base_url,
            "model": model or None,
            "api_key_configured": bool(api_key),
        }

    @staticmethod
    def _age_seconds(value: datetime | None, now: datetime) -> float | None:
        if value is None:
            return None
        return max(0.0, (now - value).total_seconds())

    def _latest_close(self, symbol: str, interval: str) -> float | None:
        latest_candle_time = self.repository.get_latest_candle_time(symbol, interval)
        if latest_candle_time is None:
            return None
        latest_candle = self.repository.get_candle(symbol, interval, latest_candle_time)
        return float(latest_candle.close) if latest_candle else None

    @staticmethod
    def _operational_risk_payload(snapshot: OperationalRiskSnapshot, now: datetime) -> dict[str, object]:
        cooldown_minutes = RiskConfig().order_cooldown_minutes
        next_order_allowed_at = (
            snapshot.last_order_at + timedelta(minutes=cooldown_minutes)
            if snapshot.last_order_at is not None
            else None
        )
        return {
            "observed_at": snapshot.observed_at,
            "orders_today": snapshot.orders_today,
            "realized_pnl_today_usdt": snapshot.realized_pnl_today_usdt,
            "last_order_at": snapshot.last_order_at,
            "next_order_allowed_at": next_order_allowed_at,
            "cooldown_active": bool(next_order_allowed_at and now < next_order_allowed_at),
        }

    @staticmethod
    def _position_payload(snapshot: OperationalRiskSnapshot, latest_close: float | None) -> dict[str, object]:
        current_exposure_usdt = (
            snapshot.position_quantity * latest_close
            if latest_close is not None
            else None
        )
        unrealized_pnl_usdt = (
            current_exposure_usdt - snapshot.position_cost_usdt
            if current_exposure_usdt is not None and snapshot.position_quantity > 0
            else None
        )
        return {
            "status": "long" if snapshot.position_quantity > 0 else "flat",
            "quantity": snapshot.position_quantity,
            "cost_usdt": snapshot.position_cost_usdt,
            "average_entry_price": snapshot.average_entry_price,
            "current_price": latest_close,
            "current_exposure_usdt": current_exposure_usdt,
            "unrealized_pnl_usdt": unrealized_pnl_usdt,
            "unrealized_pnl_pct": (
                (unrealized_pnl_usdt / snapshot.position_cost_usdt)
                if unrealized_pnl_usdt is not None and snapshot.position_cost_usdt > 0
                else None
            ),
        }

    @staticmethod
    def _chart_candle_payload(candle: Any, indicators: Any | None) -> dict[str, object]:
        values = dict(indicators.values) if indicators is not None else {}
        return {
            "time": candle.open_time,
            "open": float(candle.open),
            "high": float(candle.high),
            "low": float(candle.low),
            "close": float(candle.close),
            "volume": float(candle.volume),
            "indicators": {
                key: (float(value) if value is not None else None)
                for key, value in values.items()
            },
        }

    @classmethod
    def _order_rows(cls, entries: tuple[AgentDecisionJournalEntry, ...]) -> list[dict[str, object]]:
        sorted_entries = sorted(
            (entry for entry in entries if entry.mode == "spot_demo" and entry.exchange_order_id),
            key=lambda item: item.created_at or item.reference_time,
        )
        inventory_quantity = 0.0
        inventory_cost = 0.0
        rows: list[dict[str, object]] = []
        for entry in sorted_entries:
            order = cls._resolved_exchange_order(entry.exchange_response)
            if not order:
                continue
            executed_quantity = cls._float(order.get("executedQty"))
            quote_quantity = cls._float(order.get("cummulativeQuoteQty"))
            avg_price = quote_quantity / executed_quantity if executed_quantity > 0 else None
            side = str(order.get("side") or entry.action).lower()
            realized_pnl = None
            realized_pnl_pct = None
            if executed_quantity > 0 and quote_quantity > 0:
                if side == "buy":
                    inventory_quantity += executed_quantity
                    inventory_cost += quote_quantity
                elif side == "sell" and inventory_quantity > 0:
                    sold_quantity = min(executed_quantity, inventory_quantity)
                    allocated_cost = inventory_cost * (sold_quantity / inventory_quantity)
                    sold_quote = quote_quantity * (sold_quantity / executed_quantity)
                    realized_pnl = sold_quote - allocated_cost
                    realized_pnl_pct = realized_pnl / allocated_cost if allocated_cost > 0 else None
                    inventory_quantity -= sold_quantity
                    inventory_cost -= allocated_cost
            rows.append(
                {
                    "decision_journal_id": entry.id,
                    "cycle_id": entry.cycle_id,
                    "created_at": entry.created_at,
                    "reference_time": entry.reference_time,
                    "symbol": entry.symbol,
                    "interval": entry.interval,
                    "action": entry.action,
                    "decision_reason": entry.reason,
                    "risk_status": entry.risk_status,
                    "execution_status": entry.execution_status,
                    "exchange_order_id": entry.exchange_order_id,
                    "exchange_client_order_id": entry.exchange_client_order_id,
                    "side": side,
                    "order_status": str(order.get("status") or entry.execution_status).lower(),
                    "order_type": order.get("type"),
                    "executed_quantity": executed_quantity,
                    "quote_quantity": quote_quantity,
                    "average_price": avg_price,
                    "realized_pnl_usdt": realized_pnl,
                    "realized_pnl_pct": realized_pnl_pct,
                    "commission": cls._commission_payload(order),
                    "raw_order": order,
                }
            )
        return list(reversed(rows))

    @staticmethod
    def _float(value: object) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _commission_payload(cls, order: dict[str, Any]) -> dict[str, float]:
        totals: dict[str, float] = {}
        fills = order.get("fills")
        if not isinstance(fills, list):
            return totals
        for fill in fills:
            if not isinstance(fill, dict):
                continue
            asset = str(fill.get("commissionAsset") or "").strip()
            if not asset:
                continue
            totals[asset] = totals.get(asset, 0.0) + cls._float(fill.get("commission"))
        return totals

    @staticmethod
    def _resolved_exchange_order(exchange_response: dict[str, Any]) -> dict[str, Any]:
        if not exchange_response:
            return {}
        reconciliation = exchange_response.get("reconciliation")
        if isinstance(reconciliation, dict):
            return reconciliation
        submission = exchange_response.get("submission")
        if isinstance(submission, dict):
            return submission
        return exchange_response

    @staticmethod
    def _pnl_curve(order_rows: list[dict[str, object]]) -> list[dict[str, object]]:
        cumulative_realized = 0.0
        curve: list[dict[str, object]] = []
        for row in reversed(order_rows):
            realized = row.get("realized_pnl_usdt")
            if isinstance(realized, (int, float)):
                cumulative_realized += float(realized)
            curve.append(
                {
                    "time": row["created_at"] or row["reference_time"],
                    "exchange_order_id": row["exchange_order_id"],
                    "side": row["side"],
                    "realized_pnl_usdt": realized,
                    "cumulative_realized_pnl_usdt": cumulative_realized,
                }
            )
        return curve
