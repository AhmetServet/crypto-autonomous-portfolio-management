"""Composition root and CLI entrypoint for CAPM."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from capm.core.config import BinanceSettings, DatabaseSettings, LLMSettings
from capm.domains.market_data import HistoricalOHLCRequest, interval_to_timedelta
from capm.init_db import initialize_database
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.infra.exchange import BinanceSpotDemoTradingAdapter, BinanceSpotMarketDataAdapter
from capm.services.ingestion import BinancePublicDumpIngestionService, HistoricalMarketDataIngestionService
from capm.services.prediction_journal import PredictionJournalService
from capm.services.prediction_runtime import PredictionRuntimeService
from capm.services.trading_agent import TradingAgentService
from capm.services.llm_decision_policy import LLMDecisionPolicy
from capm.services.live_cycle import LiveTradingCycleService
from capm.domains.trading import DecisionAction, PortfolioSnapshot, ProposedDecision, RiskConfig


def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def fetch_ohlcv(
    *,
    symbol: str,
    interval: str,
    start_at: datetime,
    end_at: datetime,
    mode: str = "demo",
) -> list[dict[str, str | int]]:
    """Fetch historical OHLCV candles from Binance spot."""
    settings = BinanceSettings.from_env(mode=mode)
    adapter = BinanceSpotMarketDataAdapter(settings=settings)
    service = HistoricalMarketDataIngestionService(market_data_port=adapter)

    try:
        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol=symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
        )
        return [candle.to_dict() for candle in candles]
    finally:
        adapter.close()


def build_repository() -> TimescaleMarketDataRepository:
    """Build the configured database repository."""
    settings = DatabaseSettings.from_env()
    return TimescaleMarketDataRepository(
        settings.connection_string,
        schema_name=settings.schema_name,
        ohlcv_write_batch_size=settings.ohlcv_write_batch_size,
        hide_sql_parameters=settings.hide_sql_parameters,
    )


def print_json(payload: dict[str, object]) -> None:
    """Print a JSON response payload."""
    print(json.dumps(payload, indent=2, default=str))


def _agent_decision_payload(entry) -> dict[str, object]:
    """Build the stable CLI representation for one journaled agent decision."""
    return {
        "cycle_id": entry.cycle_id,
        "mode": entry.mode,
        "symbol": entry.symbol,
        "interval": entry.interval,
        "action": entry.action,
        "risk_status": entry.risk_status,
        "execution_status": entry.execution_status,
        "journal_id": entry.id,
    }


def _live_cycle_payload(result) -> dict[str, object]:
    """Build the stable CLI representation for one live-cycle result."""
    return {
        "status": "skipped" if result.skipped_reason else "ok",
        "cycle_time": result.cycle_time,
        "symbols": result.symbols,
        "ingested_candles": result.ingested_candles,
        "persisted_indicators": result.persisted_indicators,
        "predictions_journaled": result.predictions_journaled,
        "predictions_settled": result.predictions_settled,
        "skipped_reason": result.skipped_reason,
        "decisions": [_agent_decision_payload(entry) for entry in result.decisions],
    }


def _prediction_report_payload(entry) -> dict[str, object]:
    """Build a compact report representation for one prediction journal row."""
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


def _decision_report_payload(entry, *, include_prompts: bool = False) -> dict[str, object]:
    """Build a compact report representation for one agent decision row."""
    metadata = dict(entry.metadata)
    payload: dict[str, object] = {
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
    return payload


def _agent_report_payload(args) -> dict[str, object]:
    """Build an operational report for recent agent state."""
    repository = build_repository()
    now = datetime.now(UTC)
    symbol = args.symbol
    interval = args.interval
    latest_candle_time = repository.get_latest_candle_time(symbol, interval)
    latest_candle = None
    if latest_candle_time is not None:
        latest_candle = repository.get_candle(symbol, interval, latest_candle_time)
    latest_indicator_time = repository.get_latest_indicator_time(symbol, interval)
    latest_indicator = None
    if latest_indicator_time is not None:
        latest_indicator = repository.get_indicator_set(symbol, interval, latest_indicator_time)

    summary_start = now - timedelta(hours=args.lookback_hours)
    predictions = repository.list_recent_prediction_journal_entries(symbol, interval, args.limit)
    decisions = repository.list_recent_agent_decision_journal_entries(symbol, interval, args.limit)
    prediction_summary = PredictionJournalService(
        journal_repository=repository,
        market_data_repository=repository,
    ).summarize(
        symbol=symbol,
        interval=interval,
        start_time=summary_start,
        end_time=now,
    )
    decision_summary = repository.summarize_agent_decision_journal(
        symbol=symbol,
        interval=interval,
        start_time=summary_start,
        end_time=now,
    )
    operational_snapshot = repository.get_operational_risk_snapshot(symbol, now)
    latest_close = float(latest_candle.close) if latest_candle else None
    average_entry_price = operational_snapshot.average_entry_price
    current_exposure_usdt = (
        operational_snapshot.position_quantity * latest_close
        if latest_close is not None
        else None
    )
    unrealized_pnl_usdt = (
        current_exposure_usdt - operational_snapshot.position_cost_usdt
        if current_exposure_usdt is not None and operational_snapshot.position_quantity > 0
        else None
    )
    cooldown_minutes = RiskConfig().order_cooldown_minutes
    next_order_allowed_at = (
        operational_snapshot.last_order_at + timedelta(minutes=cooldown_minutes)
        if operational_snapshot.last_order_at is not None
        else None
    )

    portfolio = None
    if args.include_spot_demo:
        adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
        try:
            portfolio = adapter.get_portfolio(symbol).to_dict()
        finally:
            adapter.close()

    return {
        "status": "ok",
        "generated_at": now,
        "symbol": symbol,
        "interval": interval,
        "lookback_hours": args.lookback_hours,
        "market": {
            "latest_candle_time": latest_candle_time,
            "latest_candle": latest_candle.to_dict() if latest_candle else None,
            "latest_indicator_time": latest_indicator_time,
            "indicator_ready": latest_indicator.is_ready if latest_indicator else None,
            "missing_indicator_outputs": latest_indicator.missing_outputs if latest_indicator else (),
            "indicators": latest_indicator.values if latest_indicator else {},
        },
        "spot_demo_portfolio": portfolio,
        "operational_risk": {
            "observed_at": operational_snapshot.observed_at,
            "orders_today": operational_snapshot.orders_today,
            "realized_pnl_today_usdt": operational_snapshot.realized_pnl_today_usdt,
            "last_order_at": operational_snapshot.last_order_at,
            "next_order_allowed_at": next_order_allowed_at,
            "cooldown_active": bool(next_order_allowed_at and now < next_order_allowed_at),
        },
        "position": {
            "status": "long" if operational_snapshot.position_quantity > 0 else "flat",
            "quantity": operational_snapshot.position_quantity,
            "cost_usdt": operational_snapshot.position_cost_usdt,
            "average_entry_price": average_entry_price,
            "current_price": latest_close,
            "current_exposure_usdt": current_exposure_usdt,
            "unrealized_pnl_usdt": unrealized_pnl_usdt,
            "unrealized_pnl_pct": (
                (unrealized_pnl_usdt / operational_snapshot.position_cost_usdt)
                if unrealized_pnl_usdt is not None and operational_snapshot.position_cost_usdt > 0
                else None
            ),
        },
        "prediction_summary": prediction_summary.to_dict(),
        "decision_summary": decision_summary.to_dict(),
        "recent_predictions": [_prediction_report_payload(entry) for entry in predictions],
        "recent_decisions": [
            _decision_report_payload(entry, include_prompts=args.include_prompts) for entry in decisions
        ],
    }


def _parse_model_artifacts(values: list[str]) -> dict[str, tuple[Path, ...]]:
    """Parse repeated SYMBOL=PATH model-artifact CLI values."""
    parsed: dict[str, list[Path]] = {}
    for value in values:
        symbol, separator, artifact_path = value.partition("=")
        if not separator or not symbol.strip() or not artifact_path.strip():
            raise ValueError("Model artifacts must use SYMBOL=PATH format, e.g. BTCUSDT=experiments/results/run/model.pkl.")
        parsed.setdefault(symbol.strip().upper(), []).append(Path(artifact_path.strip()))
    return {symbol: tuple(paths) for symbol, paths in parsed.items()}


def _environment_flag(name: str) -> bool:
    """Read one opt-in boolean environment variable."""
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _risk_config_from_args(args) -> RiskConfig:
    """Build hard and operational trading limits from CLI arguments."""
    return RiskConfig(
        max_trade_usdt=args.max_trade_usdt,
        max_position_usdt=args.max_position_usdt,
        min_predicted_return=getattr(args, "min_predicted_return", 0.0005),
        prediction_staleness_minutes=getattr(args, "prediction_staleness_minutes", 5),
        emergency_stop=args.emergency_stop or _environment_flag("CAPM_TRADING_EMERGENCY_STOP"),
        max_daily_realized_loss_usdt=args.max_daily_realized_loss_usdt,
        max_orders_per_day=args.max_orders_per_day,
        order_cooldown_minutes=args.order_cooldown_minutes,
        max_total_exposure_usdt=args.max_total_exposure_usdt,
    )


def _add_operational_risk_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared unattended-execution risk controls."""
    parser.add_argument("--emergency-stop", action="store_true")
    parser.add_argument("--max-daily-realized-loss-usdt", type=float, default=50.0)
    parser.add_argument("--max-orders-per-day", type=int, default=20)
    parser.add_argument("--order-cooldown-minutes", type=int, default=5)
    parser.add_argument("--max-total-exposure-usdt", type=float, default=100.0)


def _add_live_cycle_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared live-cycle arguments."""
    parser.add_argument("--interval", default="1m", help="Candle interval, e.g. 1m.")
    parser.add_argument("--mode", default="dry-run", choices=["dry-run", "spot-demo"])
    parser.add_argument(
        "--model-artifact",
        action="append",
        required=True,
        help="Production model mapping in SYMBOL=PATH form. Repeat to run multiple models.",
    )
    parser.add_argument(
        "--market-data-mode",
        default="demo",
        choices=["demo", "live"],
        help="Binance public REST environment used to backfill closed candles.",
    )
    parser.add_argument(
        "--max-inline-gap-minutes",
        type=int,
        default=180,
        help="Refuse inline candle recovery beyond this duration.",
    )
    parser.add_argument(
        "--max-model-age-days",
        type=int,
        default=3,
        help="Refuse production model artifacts older than this many days.",
    )
    parser.add_argument(
        "--allow-large-gap-recovery",
        action="store_true",
        help="Explicitly allow a long REST candle backfill before the cycle continues.",
    )
    parser.add_argument(
        "--allow-stale-models",
        action="store_true",
        help="Explicitly allow stale artifacts for a non-production recovery check.",
    )
    parser.add_argument("--max-trade-usdt", type=float, default=25.0)
    parser.add_argument("--max-position-usdt", type=float, default=100.0)
    _add_operational_risk_arguments(parser)


def _seconds_until_next_cycle(*, interval: str, offset_seconds: float, now: datetime | None = None) -> float:
    """Return seconds until just after the next candle boundary."""
    current = now or datetime.now(UTC)
    normalized = current.astimezone(UTC) if current.tzinfo else current.replace(tzinfo=UTC)
    interval_seconds = int(interval_to_timedelta(interval).total_seconds())
    next_boundary = ((int(normalized.timestamp()) // interval_seconds) + 1) * interval_seconds
    return max(0.0, next_boundary + offset_seconds - normalized.timestamp())


def _build_live_cycle_service(args, *, repository=None, market_data_adapter=None, exchange_adapter=None, llm_policy=None):
    """Compose one live trading-cycle service from CLI arguments."""
    resolved_repository = repository or build_repository()
    resolved_market_data_adapter = market_data_adapter or BinanceSpotMarketDataAdapter(
        BinanceSettings.from_env(mode=args.market_data_mode)
    )
    resolved_exchange_adapter = exchange_adapter
    if resolved_exchange_adapter is None and args.mode == "spot-demo":
        resolved_exchange_adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
    resolved_llm_policy = llm_policy or LLMDecisionPolicy(LLMSettings.from_env())
    trading_agent = TradingAgentService(
        repository=resolved_repository,
        exchange_adapter=resolved_exchange_adapter,
    )
    service = LiveTradingCycleService(
        repository=resolved_repository,
        market_data_adapter=resolved_market_data_adapter,
        trading_agent=trading_agent,
        llm_policy=resolved_llm_policy,
        artifacts_by_symbol=_parse_model_artifacts(args.model_artifact),
        max_inline_gap_minutes=args.max_inline_gap_minutes,
        max_model_age_days=args.max_model_age_days,
        allow_large_gap_recovery=args.allow_large_gap_recovery,
        allow_stale_models=args.allow_stale_models,
        risk_config=_risk_config_from_args(args),
    )
    return service, resolved_market_data_adapter, resolved_exchange_adapter, resolved_llm_policy


def _run_live_loop(args, *, sleep=time.sleep, now=lambda: datetime.now(UTC)) -> None:
    """Run repeated closed-candle live cycles with bounded failure handling."""
    service, market_data_adapter, exchange_adapter, llm_policy = _build_live_cycle_service(args)
    attempted_cycles = 0
    successful_cycles = 0
    consecutive_errors = 0
    try:
        while args.max_cycles is None or attempted_cycles < args.max_cycles:
            sleep_seconds = _seconds_until_next_cycle(
                interval=args.interval,
                offset_seconds=args.cycle_offset_seconds,
                now=now(),
            )
            if sleep_seconds:
                sleep(sleep_seconds)
            started_at = now()
            attempted_cycles += 1
            try:
                result = service.run_once(interval=args.interval, mode=args.mode)
                consecutive_errors = 0
                successful_cycles += 1
                payload = _live_cycle_payload(result)
                payload["loop"] = {
                    "cycle_index": attempted_cycles,
                    "started_at": started_at,
                    "finished_at": now(),
                }
                print_json(payload)
            except (FileNotFoundError, KeyboardInterrupt):
                raise
            except Exception as exc:
                consecutive_errors += 1
                print_json(
                    {
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "cycle_index": attempted_cycles,
                        "consecutive_errors": consecutive_errors,
                        "stop_after_error_count": args.stop_after_error_count,
                    }
                )
                if consecutive_errors >= args.stop_after_error_count:
                    raise SystemExit(1) from exc
                sleep(args.sleep_after_error_seconds)
        if attempted_cycles and successful_cycles == 0 and consecutive_errors:
            raise SystemExit(1)
    finally:
        llm_policy.close()
        market_data_adapter.close()
        if exchange_adapter is not None:
            exchange_adapter.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the CAPM CLI argument parser."""
    parser = argparse.ArgumentParser(prog="capm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init-db",
        help="Initialize CAPM database schema and optional symbol tables.",
    )
    init_parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Trading pair to initialize, e.g. BTCUSDT. Can be passed more than once.",
    )

    fetch_parser = subparsers.add_parser(
        "fetch-ohlc",
        help="Fetch historical OHLCV candles from Binance spot.",
    )
    fetch_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTC/USDT.")
    fetch_parser.add_argument("--interval", required=True, help="Binance kline interval.")
    fetch_parser.add_argument(
        "--start",
        required=True,
        help="Inclusive start datetime in ISO-8601 format.",
    )
    fetch_parser.add_argument(
        "--end",
        required=True,
        help="Exclusive end datetime in ISO-8601 format.",
    )
    fetch_parser.add_argument(
        "--mode",
        default="demo",
        choices=["demo", "live"],
        help="Binance environment to query.",
    )
    fetch_parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist missing candles to the configured database instead of only printing JSON.",
    )
    fetch_parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Number of candles to write per ingestion batch when --persist is used.",
    )

    ingest_parser = subparsers.add_parser(
        "ingest-ohlcv",
        help="Ingest OHLCV candles into the configured database.",
    )
    ingest_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    ingest_parser.add_argument("--interval", required=True, help="Binance kline interval.")
    ingest_parser.add_argument("--start", required=True, help="Inclusive start datetime in ISO-8601 format.")
    ingest_parser.add_argument("--end", required=True, help="Exclusive end datetime in ISO-8601 format.")
    ingest_parser.add_argument(
        "--source",
        default="dump-with-rest-tail",
        choices=["rest", "dump", "dump-with-rest-tail"],
        help="Historical data source.",
    )
    ingest_parser.add_argument(
        "--mode",
        default="live",
        choices=["demo", "live"],
        help="Binance REST environment for REST ingestion or dump gap filling.",
    )
    ingest_parser.add_argument(
        "--batch-size",
        type=int,
        default=50_000,
        help="Number of candles to write per ingestion batch.",
    )

    predict_parser = subparsers.add_parser(
        "predict",
        help="Run one prediction from a persisted model artifact and DB-backed latest data.",
    )
    predict_parser.add_argument("--model-artifact", required=True, help="Path to model.pkl or trained_models.pkl.")
    predict_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    predict_parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    predict_parser.add_argument(
        "--at",
        default=None,
        help="Optional reference candle open time. Defaults to latest stored candle/feature row.",
    )
    predict_parser.add_argument(
        "--journal",
        action="store_true",
        help="Persist the prediction into prediction_journal and include journal_id in the output.",
    )

    settle_parser = subparsers.add_parser(
        "settle-predictions",
        help="Settle prediction journal rows whose target candles are available.",
    )
    settle_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    settle_parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    settle_parser.add_argument("--until", default=None, help="Settle predictions up to this ISO-8601 timestamp.")
    settle_parser.add_argument("--limit", type=int, default=1000, help="Maximum unsettled rows to process.")

    journal_parser = subparsers.add_parser(
        "prediction-journal",
        help="Inspect prediction journal rows.",
    )
    journal_subparsers = journal_parser.add_subparsers(dest="journal_command", required=True)
    summary_parser = journal_subparsers.add_parser(
        "summary",
        help="Summarize prediction journal quality metrics.",
    )
    summary_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    summary_parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    summary_parser.add_argument("--start", required=True, help="Inclusive start datetime in ISO-8601 format.")
    summary_parser.add_argument("--end", required=True, help="Exclusive end datetime in ISO-8601 format.")
    summary_parser.add_argument("--model-name", default=None, help="Optional model name filter.")

    agent_parser = subparsers.add_parser("agent", help="Run and inspect Spot Demo trading-agent cycles.")
    agent_subparsers = agent_parser.add_subparsers(dest="agent_command", required=True)
    run_once_parser = agent_subparsers.add_parser("run-once", help="Run one auditable trading-agent cycle.")
    run_once_parser.add_argument("--symbol", default=None, help="Trading pair for threshold policy, e.g. BTCUSDT.")
    run_once_parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    run_once_parser.add_argument("--mode", default="dry-run", choices=["dry-run", "spot-demo"])
    run_once_parser.add_argument("--policy", default="threshold", choices=["threshold", "llm"])
    run_once_parser.add_argument(
        "--show-prompt",
        action="store_true",
        help="Include the exact LLM system and user prompts in the CLI output.",
    )
    run_once_parser.add_argument("--dry-run-usdt-balance", type=float, default=1000.0)
    run_once_parser.add_argument("--dry-run-base-asset-balance", type=float, default=0.0)
    run_once_parser.add_argument("--max-trade-usdt", type=float, default=25.0)
    run_once_parser.add_argument("--max-position-usdt", type=float, default=100.0)
    run_once_parser.add_argument("--min-predicted-return", type=float, default=0.0005)
    run_once_parser.add_argument("--prediction-staleness-minutes", type=int, default=5)
    _add_operational_risk_arguments(run_once_parser)
    live_once_parser = agent_subparsers.add_parser(
        "run-live-once",
        help="Refresh closed candles, journal predictions, and run one LLM trading cycle.",
    )
    _add_live_cycle_arguments(live_once_parser)
    run_loop_parser = agent_subparsers.add_parser(
        "run-loop",
        help="Continuously run closed-candle live cycles.",
    )
    _add_live_cycle_arguments(run_loop_parser)
    run_loop_parser.add_argument(
        "--cycle-offset-seconds",
        type=float,
        default=2.0,
        help="Seconds after candle close before each cycle starts.",
    )
    run_loop_parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Stop after this many cycles. Omit to run until interrupted.",
    )
    run_loop_parser.add_argument("--stop-after-error-count", type=int, default=3)
    run_loop_parser.add_argument("--sleep-after-error-seconds", type=float, default=10.0)
    report_parser = agent_subparsers.add_parser("report", help="Show recent agent, prediction, risk, and market state.")
    report_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    report_parser.add_argument("--interval", default="1m", help="Candle interval, e.g. 1m.")
    report_parser.add_argument("--limit", type=int, default=20, help="Recent prediction/decision rows to include.")
    report_parser.add_argument("--lookback-hours", type=float, default=24.0, help="Summary window ending now.")
    report_parser.add_argument("--include-prompts", action="store_true", help="Include stored LLM prompts and raw responses.")
    report_parser.add_argument("--include-spot-demo", action="store_true", help="Read current Spot Demo portfolio balances.")
    agent_journal_parser = agent_subparsers.add_parser("journal", help="Inspect agent decision journal rows.")
    agent_journal_subparsers = agent_journal_parser.add_subparsers(dest="agent_journal_command", required=True)
    agent_summary_parser = agent_journal_subparsers.add_parser("summary", help="Summarize agent decision journal rows.")
    agent_summary_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    agent_summary_parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    agent_summary_parser.add_argument("--start", required=True, help="Inclusive start datetime in ISO-8601 format.")
    agent_summary_parser.add_argument("--end", required=True, help="Exclusive end datetime in ISO-8601 format.")

    spot_demo_parser = subparsers.add_parser("spot-demo", help="Run explicit Binance Spot Demo smoke tests.")
    spot_demo_subparsers = spot_demo_parser.add_subparsers(dest="spot_demo_command", required=True)
    spot_demo_account_parser = spot_demo_subparsers.add_parser("account", help="Read Spot Demo balances without submitting an order.")
    spot_demo_account_parser.add_argument("--symbol", default="BTCUSDT", help="USDT trading pair, e.g. BTCUSDT.")
    spot_demo_buy_parser = spot_demo_subparsers.add_parser("test-market-buy", help="Submit one confirmed Spot Demo market buy.")
    spot_demo_buy_parser.add_argument("--symbol", default="BTCUSDT", help="USDT trading pair, e.g. BTCUSDT.")
    spot_demo_buy_parser.add_argument("--usdt-amount", type=float, required=True, help="Quote-currency amount to spend.")
    spot_demo_buy_parser.add_argument("--confirm", action="store_true", help="Required acknowledgement that a Spot Demo order will be submitted.")

    return parser


def main() -> None:
    """Run the CAPM CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "init-db":
        repository = initialize_database(args.symbol)
        print_json(
            {
                "status": "ok",
                "database": repository._engine.url.database or "configured database",
                "symbols": args.symbol,
            }
        )
        return

    if args.command == "fetch-ohlc" and not args.persist:
        candles = fetch_ohlcv(
            symbol=args.symbol,
            interval=args.interval,
            start_at=parse_datetime(args.start),
            end_at=parse_datetime(args.end),
            mode=args.mode,
        )
        print(json.dumps(candles, indent=2))
        return

    if args.command == "fetch-ohlc" and args.persist:
        repository = initialize_database([args.symbol])
        adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=args.mode))
        try:
            service = HistoricalMarketDataIngestionService(
                market_data_port=adapter,
                repository_port=repository,
                persist_batch_candle_count=args.batch_size,
            )
            result = service.ingest_ohlcv(
                HistoricalOHLCRequest(
                    symbol=args.symbol,
                    interval=args.interval,
                    start_at=parse_datetime(args.start),
                    end_at=parse_datetime(args.end),
                )
            )
            print_json(
                {
                    "status": "ok",
                    "source": "rest",
                    "fetched_count": result.fetched_count,
                    "stored_count": result.stored_count,
                    "latest": repository.get_latest_candle_time(args.symbol, args.interval),
                }
            )
        finally:
            adapter.close()
        return

    if args.command == "ingest-ohlcv":
        request = HistoricalOHLCRequest(
            symbol=args.symbol,
            interval=args.interval,
            start_at=parse_datetime(args.start),
            end_at=parse_datetime(args.end),
        )
        repository = initialize_database([request.symbol])

        if args.source == "rest":
            adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=args.mode))
            try:
                service = HistoricalMarketDataIngestionService(
                    market_data_port=adapter,
                    repository_port=repository,
                    persist_batch_candle_count=args.batch_size,
                )
                result = service.ingest_ohlcv(request)
                print_json(
                    {
                        "status": "ok",
                        "source": "rest",
                        "stored_count": result.stored_count,
                        "fetched_count": result.fetched_count,
                        "latest": repository.get_latest_candle_time(request.symbol, request.interval),
                    }
                )
            finally:
                adapter.close()
            return

        rest_adapter = None
        if args.source == "dump-with-rest-tail":
            rest_adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=args.mode))
        service = BinancePublicDumpIngestionService(
            repository_port=repository,
            rest_adapter=rest_adapter,
            persist_batch_candle_count=args.batch_size,
        )
        try:
            result = service.ingest_ohlcv(
                request,
                include_rest_tail=args.source == "dump-with-rest-tail",
            )
            print_json(
                {
                    "status": "ok",
                    "source": args.source,
                    "downloaded_files": result.downloaded_files,
                    "skipped_files": result.skipped_files,
                    "coverage_skipped_files": result.coverage_skipped_files,
                    "dump_rows": result.dump_rows,
                    "rest_rows": result.rest_rows,
                    "stored_rows": result.stored_rows,
                    "elapsed_seconds": result.elapsed_seconds,
                    "latest": repository.get_latest_candle_time(request.symbol, request.interval),
                }
            )
        finally:
            service.close()
            if rest_adapter is not None:
                rest_adapter.close()
        return

    if args.command == "predict":
        repository = build_repository()
        runtime = PredictionRuntimeService(repository)
        prediction = runtime.predict(
            artifact_path=args.model_artifact,
            symbol=args.symbol,
            interval=args.interval,
            reference_time=parse_datetime(args.at) if args.at else None,
        )
        payload = prediction.to_dict()
        if args.journal:
            journal_entry = PredictionJournalService(
                journal_repository=repository,
                market_data_repository=repository,
            ).journal_prediction(prediction)
            payload["journal_id"] = journal_entry.id
        print_json({"status": "ok", "prediction": payload})
        return

    if args.command == "settle-predictions":
        repository = build_repository()
        until = parse_datetime(args.until) if args.until else datetime.now(UTC) - interval_to_timedelta(args.interval)
        result = PredictionJournalService(
            journal_repository=repository,
            market_data_repository=repository,
        ).settle_predictions(
            symbol=args.symbol,
            interval=args.interval,
            until=until,
            limit=args.limit,
        )
        print_json({"status": "ok", **result})
        return

    if args.command == "prediction-journal" and args.journal_command == "summary":
        repository = build_repository()
        summary = PredictionJournalService(
            journal_repository=repository,
            market_data_repository=repository,
        ).summarize(
            symbol=args.symbol,
            interval=args.interval,
            start_time=parse_datetime(args.start),
            end_time=parse_datetime(args.end),
            model_name=args.model_name,
        )
        print_json({"status": "ok", "summary": summary.to_dict()})
        return

    if args.command == "spot-demo":
        if args.spot_demo_command == "test-market-buy":
            if args.usdt_amount <= 0:
                parser.error("spot-demo test-market-buy --usdt-amount must be greater than zero")
            if not args.confirm:
                parser.error("spot-demo test-market-buy requires --confirm")
        adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
        try:
            before = adapter.get_portfolio(args.symbol)
            if args.spot_demo_command == "account":
                print_json({"status": "ok", "symbol": args.symbol, "portfolio": before.to_dict()})
                return
            response = adapter.submit_market_order(
                args.symbol,
                ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=args.usdt_amount),
            )
            after = adapter.get_portfolio(args.symbol)
            print_json(
                {
                    "status": "ok",
                    "symbol": args.symbol,
                    "usdt_amount": args.usdt_amount,
                    "portfolio_before": before.to_dict(),
                    "order": response,
                    "portfolio_after": after.to_dict(),
                }
            )
        finally:
            adapter.close()
        return

    if args.command == "agent" and args.agent_command == "run-once":
        repository = build_repository()
        portfolio = PortfolioSnapshot(
            available_usdt=args.dry_run_usdt_balance,
            base_asset_free=args.dry_run_base_asset_balance,
        )
        risk_config = _risk_config_from_args(args)
        exchange_adapter = None
        if args.mode == "spot-demo":
            exchange_adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
        service = TradingAgentService(repository=repository, exchange_adapter=exchange_adapter)
        if args.policy == "llm":
            llm_policy = LLMDecisionPolicy(LLMSettings.from_env())
            try:
                entries = service.run_llm_once(
                    interval=args.interval,
                    mode=args.mode,
                    portfolio=portfolio,
                    risk_config=risk_config,
                    llm_policy=llm_policy,
                )
            finally:
                llm_policy.close()
                if exchange_adapter is not None:
                    exchange_adapter.close()
        else:
            if not args.symbol:
                parser.error("agent run-once --policy threshold requires --symbol")
            entries = (
                service.run_once(
                    symbol=args.symbol,
                    interval=args.interval,
                    mode=args.mode,
                    portfolio=portfolio,
                    risk_config=risk_config,
                ),
            )
            if exchange_adapter is not None:
                exchange_adapter.close()
        payload = {"status": "ok", "decisions": [_agent_decision_payload(entry) for entry in entries]}
        if args.show_prompt:
            if args.policy != "llm":
                parser.error("agent run-once --show-prompt requires --policy llm")
            batch = service.last_llm_batch
            if batch is None:
                raise RuntimeError("LLM prompt metadata was not produced.")
            payload["llm"] = {
                "system_prompt": batch.system_prompt,
                "prompt": batch.prompt,
                "raw_response": batch.raw_response,
                "attempts": batch.attempts,
                "model": batch.model,
                "provider_host": batch.provider_host,
                "latency_seconds": batch.latency_seconds,
                "usage": batch.usage,
            }
        print_json(payload)
        return

    if args.command == "agent" and args.agent_command == "run-live-once":
        service, market_data_adapter, exchange_adapter, llm_policy = _build_live_cycle_service(args)
        try:
            result = service.run_once(interval=args.interval, mode=args.mode)
            print_json(_live_cycle_payload(result))
        finally:
            llm_policy.close()
            market_data_adapter.close()
            if exchange_adapter is not None:
                exchange_adapter.close()
        return

    if args.command == "agent" and args.agent_command == "run-loop":
        if args.max_cycles is not None and args.max_cycles < 1:
            parser.error("agent run-loop --max-cycles must be greater than zero")
        if args.stop_after_error_count < 1:
            parser.error("agent run-loop --stop-after-error-count must be greater than zero")
        if args.cycle_offset_seconds < 0 or args.sleep_after_error_seconds < 0:
            parser.error("agent run-loop sleep values cannot be negative")
        _run_live_loop(args)
        return

    if args.command == "agent" and args.agent_command == "report":
        if args.limit < 1:
            parser.error("agent report --limit must be greater than zero")
        if args.lookback_hours <= 0:
            parser.error("agent report --lookback-hours must be greater than zero")
        print_json(_agent_report_payload(args))
        return

    if args.command == "agent" and args.agent_command == "journal" and args.agent_journal_command == "summary":
        repository = build_repository()
        summary = repository.summarize_agent_decision_journal(
            symbol=args.symbol,
            interval=args.interval,
            start_time=parse_datetime(args.start),
            end_time=parse_datetime(args.end),
        )
        print_json({"status": "ok", "summary": summary.to_dict()})
        return
