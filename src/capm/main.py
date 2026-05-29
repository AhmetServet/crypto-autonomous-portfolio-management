"""Composition root and CLI entrypoint for CAPM."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from capm.core.config import BinanceSettings, DatabaseSettings
from capm.domains.market_data import HistoricalOHLCRequest, interval_to_timedelta
from capm.init_db import initialize_database
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.infra.exchange import BinanceSpotMarketDataAdapter
from capm.services.ingestion import BinancePublicDumpIngestionService, HistoricalMarketDataIngestionService
from capm.services.prediction_journal import PredictionJournalService
from capm.services.prediction_runtime import PredictionRuntimeService


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
