"""Composition root and CLI entrypoint for CAPM."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
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


def _parse_model_artifacts(values: list[str]) -> dict[str, tuple[Path, ...]]:
    """Parse repeated SYMBOL=PATH model-artifact CLI values."""
    parsed: dict[str, list[Path]] = {}
    for value in values:
        symbol, separator, artifact_path = value.partition("=")
        if not separator or not symbol.strip() or not artifact_path.strip():
            raise ValueError("Model artifacts must use SYMBOL=PATH format, e.g. BTCUSDT=experiments/results/run/model.pkl.")
        parsed.setdefault(symbol.strip().upper(), []).append(Path(artifact_path.strip()))
    return {symbol: tuple(paths) for symbol, paths in parsed.items()}


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
    live_once_parser = agent_subparsers.add_parser(
        "run-live-once",
        help="Refresh closed candles, journal predictions, and run one LLM trading cycle.",
    )
    live_once_parser.add_argument("--interval", default="1m", help="Candle interval, e.g. 1m.")
    live_once_parser.add_argument("--mode", default="dry-run", choices=["dry-run", "spot-demo"])
    live_once_parser.add_argument(
        "--model-artifact",
        action="append",
        required=True,
        help="Production model mapping in SYMBOL=PATH form. Repeat to run multiple models.",
    )
    live_once_parser.add_argument(
        "--market-data-mode",
        default="demo",
        choices=["demo", "live"],
        help="Binance public REST environment used to backfill closed candles.",
    )
    live_once_parser.add_argument(
        "--max-inline-gap-minutes",
        type=int,
        default=180,
        help="Refuse inline candle recovery beyond this duration.",
    )
    live_once_parser.add_argument(
        "--max-model-age-days",
        type=int,
        default=3,
        help="Refuse production model artifacts older than this many days.",
    )
    live_once_parser.add_argument(
        "--allow-large-gap-recovery",
        action="store_true",
        help="Explicitly allow a long REST candle backfill before the cycle continues.",
    )
    live_once_parser.add_argument(
        "--allow-stale-models",
        action="store_true",
        help="Explicitly allow stale artifacts for a non-production recovery check.",
    )
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
        risk_config = RiskConfig(
            max_trade_usdt=args.max_trade_usdt,
            max_position_usdt=args.max_position_usdt,
            min_predicted_return=args.min_predicted_return,
            prediction_staleness_minutes=args.prediction_staleness_minutes,
        )
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
        repository = build_repository()
        market_data_adapter = BinanceSpotMarketDataAdapter(
            BinanceSettings.from_env(mode=args.market_data_mode)
        )
        exchange_adapter = (
            BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
            if args.mode == "spot-demo"
            else None
        )
        llm_policy = LLMDecisionPolicy(LLMSettings.from_env())
        try:
            trading_agent = TradingAgentService(
                repository=repository,
                exchange_adapter=exchange_adapter,
            )
            result = LiveTradingCycleService(
                repository=repository,
                market_data_adapter=market_data_adapter,
                trading_agent=trading_agent,
                llm_policy=llm_policy,
                artifacts_by_symbol=_parse_model_artifacts(args.model_artifact),
                max_inline_gap_minutes=args.max_inline_gap_minutes,
                max_model_age_days=args.max_model_age_days,
                allow_large_gap_recovery=args.allow_large_gap_recovery,
                allow_stale_models=args.allow_stale_models,
            ).run_once(interval=args.interval, mode=args.mode)
            print_json(
                {
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
            )
        finally:
            llm_policy.close()
            market_data_adapter.close()
            if exchange_adapter is not None:
                exchange_adapter.close()
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
