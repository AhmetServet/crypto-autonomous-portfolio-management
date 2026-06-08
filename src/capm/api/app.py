"""FastAPI application for CAPM dashboard reads."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from capm.core.config import BinanceSettings
from capm.domains.market_data import HistoricalOHLCRequest, interval_to_timedelta
from capm.domains.trading import DecisionAction, ProposedDecision
from capm.infra.exchange import BinanceSpotDemoTradingAdapter
from capm.infra.exchange import BinanceSpotMarketDataAdapter
from capm.init_db import initialize_database
from capm.main import (
    _agent_decision_payload,
    _build_live_cycle_service,
    _live_cycle_payload,
    _risk_config_from_args,
    build_repository,
    fetch_ohlcv,
    parse_datetime,
)
from capm.services.dashboard import DashboardReportRequest, DashboardReportService
from capm.services.ingestion import BinancePublicDumpIngestionService, HistoricalMarketDataIngestionService
from capm.services.features import IndicatorPipelineService
from capm.services.llm_decision_policy import LLMDecisionPolicy
from capm.services.live_cycle import default_live_indicator_specs
from capm.core.config import LLMSettings
from capm.services.prediction_journal import PredictionJournalService
from capm.services.prediction_runtime import PredictionRuntimeService
from capm.services.trading_agent import TradingAgentService
from capm.domains.trading import PortfolioSnapshot


def get_dashboard_service() -> DashboardReportService:
    """Build the dashboard service from environment-backed repository settings."""
    return DashboardReportService(build_repository())


def get_spot_demo_adapter() -> BinanceSpotDemoTradingAdapter:
    """Build an authenticated Spot Demo trading adapter."""
    return BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))


DashboardServiceDependency = Annotated[DashboardReportService, Depends(get_dashboard_service)]
SpotDemoAdapterDependency = Annotated[BinanceSpotDemoTradingAdapter, Depends(get_spot_demo_adapter)]
MODEL_RESULTS_DIR = Path("experiments/results")


def _risk_args_from_request(request: AgentRunOnceRequest | LiveCycleRunOnceRequest) -> SimpleNamespace:
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


def _time_range_payload(item) -> dict[str, object]:
    return {
        "start": item.start_time,
        "end": item.end_time,
    }


def _coverage_range_payload(item) -> dict[str, object]:
    return {
        "coinpair_id": item.coinpair_id,
        "table_name": item.table_name,
        "symbol": item.symbol,
        "interval": item.interval,
        "start": item.start_open_time,
        "end": item.end_open_time,
    }


def _discover_model_artifacts(
    *,
    symbol: str | None = None,
    interval: str | None = None,
    results_dir: Path | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Return trained model artifacts from local experiment results."""
    results_dir = results_dir or MODEL_RESULTS_DIR
    artifacts: list[dict[str, object]] = []
    if not results_dir.exists():
        return {"status": "ok", "results_dir": str(results_dir), "artifacts": [], "latest_by_model": []}

    normalized_symbol = symbol.strip().upper() if symbol else None
    normalized_interval = interval.strip() if interval else None
    for summary_path in sorted(results_dir.glob("*/summary.json"), reverse=True):
        try:
            summary = json.loads(summary_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        request = summary.get("request") if isinstance(summary.get("request"), dict) else {}
        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
        if not metrics:
            metrics = summary.get("aggregate_metrics") if isinstance(summary.get("aggregate_metrics"), dict) else {}
        backtest = summary.get("backtest") if isinstance(summary.get("backtest"), dict) else {}

        artifact_path = Path(str(summary.get("model_artifact_path") or summary_path.parent / "model.pkl"))
        artifact_kind = "production"
        if not artifact_path.is_file():
            walk_forward_artifact_path = summary_path.parent / "trained_models.pkl"
            if not walk_forward_artifact_path.is_file():
                continue
            artifact_path = walk_forward_artifact_path
            artifact_kind = "walk_forward"
        if not artifact_path.is_file():
            continue

        artifact_symbol = str(summary.get("symbol") or request.get("symbol") or "").upper()
        artifact_interval = str(summary.get("interval") or request.get("interval") or "")
        if normalized_symbol and artifact_symbol != normalized_symbol:
            continue
        if normalized_interval and artifact_interval != normalized_interval:
            continue

        stat = artifact_path.stat()
        artifacts.append(
            {
                "run_id": summary.get("run_id") or summary_path.parent.name,
                "symbol": artifact_symbol,
                "interval": artifact_interval,
                "model_name": summary.get("model_name") or request.get("model_name"),
                "artifact_kind": artifact_kind,
                "artifact_path": str(artifact_path),
                "summary_path": str(summary_path),
                "trained_through": summary.get("end_time") or request.get("end_time"),
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "direction_accuracy": metrics.get("direction_accuracy"),
                "mape": metrics.get("mape"),
                "rmse": metrics.get("rmse"),
                "cumulative_return": backtest.get("cumulative_return"),
                "trade_count": backtest.get("trade_count"),
            }
        )

    artifacts.sort(key=lambda item: str(item["modified_at"]), reverse=True)
    latest_by_model: dict[str, dict[str, object]] = {}
    for artifact in artifacts:
        model_name = str(artifact.get("model_name") or artifact["run_id"])
        latest_by_model.setdefault(model_name, artifact)
    return {
        "status": "ok",
        "results_dir": str(results_dir),
        "artifacts": artifacts[:limit],
        "latest_by_model": list(latest_by_model.values()),
    }


class SpotDemoMarketBuyRequest(BaseModel):
    """Manual Spot Demo market-buy request."""

    symbol: str = Field(default="BTCUSDT", min_length=1)
    usdt_amount: float = Field(gt=0)
    confirm: bool = False


class SpotDemoMarketSellRequest(BaseModel):
    """Manual Spot Demo market-sell request."""

    symbol: str = Field(default="BTCUSDT", min_length=1)
    quantity: float = Field(gt=0)
    confirm: bool = False


class LiveCycleRunOnceRequest(BaseModel):
    """Request body for one closed-candle agent cycle."""

    interval: str = Field(default="1m", min_length=1)
    mode: str = Field(default="dry-run", pattern="^(dry-run|spot-demo)$")
    model_artifacts: list[str] = Field(min_length=1)
    market_data_mode: str = Field(default="demo", pattern="^(demo|live)$")
    max_inline_gap_minutes: int = Field(default=180, ge=1)
    max_model_age_days: int = Field(default=3, ge=1)
    allow_large_gap_recovery: bool = False
    allow_stale_models: bool = False
    max_trade_usdt: float = Field(default=25.0, gt=0)
    max_position_usdt: float = Field(default=100.0, gt=0)
    emergency_stop: bool = False
    max_daily_realized_loss_usdt: float = Field(default=50.0, gt=0)
    max_orders_per_day: int = Field(default=20, ge=1)
    order_cooldown_minutes: int = Field(default=5, ge=0)
    max_total_exposure_usdt: float = Field(default=100.0, gt=0)


class InitDatabaseRequest(BaseModel):
    """Initialize database metadata and optional symbol tables."""

    symbols: list[str] = Field(default_factory=list)


class FetchOHLCVRequest(BaseModel):
    """Fetch historical candles, optionally persisting missing rows."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    mode: str = Field(default="demo", pattern="^(demo|live)$")
    persist: bool = False
    batch_size: int = Field(default=10_000, ge=1)


class IngestOHLCVRequest(BaseModel):
    """Ingest OHLCV candles from REST or public dumps."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    source: str = Field(default="dump-with-rest-tail", pattern="^(rest|dump|dump-with-rest-tail)$")
    mode: str = Field(default="live", pattern="^(demo|live)$")
    batch_size: int = Field(default=50_000, ge=1)


class RepairOHLCVGapsRequest(BaseModel):
    """Repair missing OHLCV coverage gaps inside a requested range."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    mode: str = Field(default="demo", pattern="^(demo|live)$")
    batch_size: int = Field(default=50_000, ge=1)


class BackfillIndicatorsRequest(BaseModel):
    """Compute and persist indicator rows for stored candles."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    chunk_candle_count: int = Field(default=10_000, ge=1)
    resume_from_latest: bool = True


class PredictRequest(BaseModel):
    """Run one persisted model artifact against DB-backed data."""

    model_artifact: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    at: str | None = None
    journal: bool = False


class SettlePredictionsRequest(BaseModel):
    """Settle prediction journal rows whose target candles are available."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    until: str | None = None
    limit: int = Field(default=1000, ge=1)


class JournalSummaryRequest(BaseModel):
    """Summarize prediction or agent journal rows."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    model_name: str | None = None


class AgentRunOnceRequest(BaseModel):
    """Run one threshold or LLM policy trading-agent cycle."""

    symbol: str | None = None
    interval: str = Field(default="1m", min_length=1)
    mode: str = Field(default="dry-run", pattern="^(dry-run|spot-demo)$")
    policy: str = Field(default="threshold", pattern="^(threshold|llm)$")
    show_prompt: bool = False
    dry_run_usdt_balance: float = Field(default=1000.0, ge=0)
    dry_run_base_asset_balance: float = Field(default=0.0, ge=0)
    max_trade_usdt: float = Field(default=25.0, gt=0)
    max_position_usdt: float = Field(default=100.0, gt=0)
    min_predicted_return: float = 0.0005
    prediction_staleness_minutes: int = Field(default=5, ge=1)
    emergency_stop: bool = False
    max_daily_realized_loss_usdt: float = Field(default=50.0, gt=0)
    max_orders_per_day: int = Field(default=20, ge=1)
    order_cooldown_minutes: int = Field(default=5, ge=0)
    max_total_exposure_usdt: float = Field(default=100.0, gt=0)


def create_app() -> FastAPI:
    """Create the dashboard API application."""
    app = FastAPI(title="CAPM Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health(service: DashboardServiceDependency) -> object:
        return jsonable_encoder(service.health())

    @app.get("/api/symbols")
    def symbols(
        service: DashboardServiceDependency,
        interval: str = Query(default="1m", min_length=1),
    ) -> object:
        return jsonable_encoder(service.list_symbols(interval=interval))

    @app.get("/api/model-artifacts")
    def model_artifacts(
        symbol: str | None = Query(default=None, min_length=1),
        interval: str | None = Query(default=None, min_length=1),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> object:
        return jsonable_encoder(_discover_model_artifacts(symbol=symbol, interval=interval, limit=limit))

    @app.post("/api/database/init")
    def init_database(request: InitDatabaseRequest) -> object:
        repository = initialize_database(request.symbols)
        return jsonable_encoder(
            {
                "status": "ok",
                "database": repository._engine.url.database or "configured database",
                "symbols": request.symbols,
            }
        )

    @app.post("/api/market/fetch-ohlcv")
    def market_fetch_ohlcv(request: FetchOHLCVRequest) -> object:
        if not request.persist:
            candles = fetch_ohlcv(
                symbol=request.symbol,
                interval=request.interval,
                start_at=parse_datetime(request.start),
                end_at=parse_datetime(request.end),
                mode=request.mode,
            )
            return jsonable_encoder({"status": "ok", "persisted": False, "candles": candles})

        repository = initialize_database([request.symbol])
        adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=request.mode))
        try:
            service = HistoricalMarketDataIngestionService(
                market_data_port=adapter,
                repository_port=repository,
                persist_batch_candle_count=request.batch_size,
            )
            result = service.ingest_ohlcv(
                HistoricalOHLCRequest(
                    symbol=request.symbol,
                    interval=request.interval,
                    start_at=parse_datetime(request.start),
                    end_at=parse_datetime(request.end),
                )
            )
            return jsonable_encoder(
                {
                    "status": "ok",
                    "source": "rest",
                    "persisted": True,
                    "fetched_count": result.fetched_count,
                    "stored_count": result.stored_count,
                    "latest": repository.get_latest_candle_time(request.symbol, request.interval),
                }
            )
        finally:
            adapter.close()

    @app.post("/api/market/ingest-ohlcv")
    def market_ingest_ohlcv(request: IngestOHLCVRequest) -> object:
        ohlcv_request = HistoricalOHLCRequest(
            symbol=request.symbol,
            interval=request.interval,
            start_at=parse_datetime(request.start),
            end_at=parse_datetime(request.end),
        )
        repository = initialize_database([ohlcv_request.symbol])

        if request.source == "rest":
            adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=request.mode))
            try:
                service = HistoricalMarketDataIngestionService(
                    market_data_port=adapter,
                    repository_port=repository,
                    persist_batch_candle_count=request.batch_size,
                )
                result = service.ingest_ohlcv(ohlcv_request)
                return jsonable_encoder(
                    {
                        "status": "ok",
                        "source": "rest",
                        "stored_count": result.stored_count,
                        "fetched_count": result.fetched_count,
                        "latest": repository.get_latest_candle_time(ohlcv_request.symbol, ohlcv_request.interval),
                    }
                )
            finally:
                adapter.close()

        rest_adapter = None
        if request.source == "dump-with-rest-tail":
            rest_adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=request.mode))
        service = BinancePublicDumpIngestionService(
            repository_port=repository,
            rest_adapter=rest_adapter,
            persist_batch_candle_count=request.batch_size,
        )
        try:
            result = service.ingest_ohlcv(
                ohlcv_request,
                include_rest_tail=request.source == "dump-with-rest-tail",
            )
            return jsonable_encoder(
                {
                    "status": "ok",
                    "source": request.source,
                    "downloaded_files": result.downloaded_files,
                    "skipped_files": result.skipped_files,
                    "coverage_skipped_files": result.coverage_skipped_files,
                    "dump_rows": result.dump_rows,
                    "rest_rows": result.rest_rows,
                    "stored_rows": result.stored_rows,
                    "elapsed_seconds": result.elapsed_seconds,
                    "latest": repository.get_latest_candle_time(ohlcv_request.symbol, ohlcv_request.interval),
                }
            )
        finally:
            service.close()
            if rest_adapter is not None:
                rest_adapter.close()

    @app.get("/api/data/coverage")
    def data_coverage(
        symbol: str = Query(min_length=1),
        interval: str = Query(default="1m", min_length=1),
        start: str = Query(min_length=1),
        end: str = Query(min_length=1),
    ) -> object:
        repository = build_repository()
        start_time = parse_datetime(start)
        end_time = parse_datetime(end)
        interval_delta = interval_to_timedelta(interval)
        ohlcv_plan = repository.plan_candle_fetch(symbol, interval, start_time, end_time)
        indicator_ranges = repository._load_coverage_ranges("indicator", symbol, interval, start_time, end_time)
        feature_ranges = repository._load_coverage_ranges("feature", symbol, interval, start_time, end_time)
        indicator_missing = repository._build_missing_ranges(indicator_ranges, interval_delta, start_time, end_time)
        feature_missing = repository._build_missing_ranges(feature_ranges, interval_delta, start_time, end_time)
        return jsonable_encoder(
            {
                "status": "ok",
                "symbol": symbol.upper(),
                "interval": interval,
                "start": start_time,
                "end": end_time,
                "ohlcv": {
                    "covered_ranges": [_coverage_range_payload(item) for item in ohlcv_plan.covered_ranges],
                    "missing_ranges": [_time_range_payload(item) for item in ohlcv_plan.missing_ranges],
                },
                "indicators": {
                    "covered_ranges": [_coverage_range_payload(item) for item in indicator_ranges],
                    "missing_ranges": [_time_range_payload(item) for item in indicator_missing],
                },
                "features": {
                    "covered_ranges": [_coverage_range_payload(item) for item in feature_ranges],
                    "missing_ranges": [_time_range_payload(item) for item in feature_missing],
                },
            }
        )

    @app.post("/api/market/repair-ohlcv-gaps")
    def repair_ohlcv_gaps(request: RepairOHLCVGapsRequest) -> object:
        repository = initialize_database([request.symbol])
        start_time = parse_datetime(request.start)
        end_time = parse_datetime(request.end)
        plan = repository.plan_candle_fetch(request.symbol, request.interval, start_time, end_time)
        if not plan.missing_ranges:
            return jsonable_encoder({"status": "ok", "repaired_ranges": 0, "fetched_count": 0, "stored_count": 0})

        adapter = BinanceSpotMarketDataAdapter(settings=BinanceSettings.from_env(mode=request.mode))
        service = HistoricalMarketDataIngestionService(
            market_data_port=adapter,
            repository_port=repository,
            persist_batch_candle_count=request.batch_size,
        )
        fetched_count = 0
        stored_count = 0
        try:
            for gap in plan.missing_ranges:
                result = service.ingest_ohlcv(
                    HistoricalOHLCRequest(
                        symbol=request.symbol,
                        interval=request.interval,
                        start_at=gap.start_time,
                        end_at=gap.end_time,
                    )
                )
                fetched_count += result.fetched_count
                stored_count += result.stored_count
            return jsonable_encoder(
                {
                    "status": "ok",
                    "repaired_ranges": len(plan.missing_ranges),
                    "fetched_count": fetched_count,
                    "stored_count": stored_count,
                    "latest": repository.get_latest_candle_time(request.symbol, request.interval),
                }
            )
        finally:
            adapter.close()

    @app.post("/api/features/backfill-indicators")
    def backfill_indicators(request: BackfillIndicatorsRequest) -> object:
        repository = build_repository()
        service = IndicatorPipelineService(
            market_data_repository=repository,
            feature_repository=repository,
            feature_window_reader=repository,
        )
        result = service.backfill_feature_range(
            symbol=request.symbol,
            interval=request.interval,
            start_time=parse_datetime(request.start),
            end_time=parse_datetime(request.end),
            indicator_specs=default_live_indicator_specs(),
            chunk_candle_count=request.chunk_candle_count,
            resume_from_latest=request.resume_from_latest,
        )
        return jsonable_encoder(
            {
                "status": "ok",
                "requested_start_time": result.requested_start_time,
                "effective_start_time": result.effective_start_time,
                "end_time": result.end_time,
                "resumed_from": result.resumed_from,
                "chunks_processed": result.chunks_processed,
                "candles_read": result.candles_read,
                "indicator_rows_persisted": result.indicator_rows_persisted,
                "last_persisted_open_time": result.last_persisted_open_time,
            }
        )

    @app.post("/api/predict")
    def predict(request: PredictRequest) -> object:
        repository = build_repository()
        runtime = PredictionRuntimeService(repository)
        prediction = runtime.predict(
            artifact_path=request.model_artifact,
            symbol=request.symbol,
            interval=request.interval,
            reference_time=parse_datetime(request.at) if request.at else None,
        )
        payload = prediction.to_dict()
        if request.journal:
            journal_entry = PredictionJournalService(
                journal_repository=repository,
                market_data_repository=repository,
            ).journal_prediction(prediction)
            payload["journal_id"] = journal_entry.id
        return jsonable_encoder({"status": "ok", "prediction": payload})

    @app.post("/api/predictions/settle")
    def settle_predictions(request: SettlePredictionsRequest) -> object:
        repository = build_repository()
        until = parse_datetime(request.until) if request.until else datetime_now_minus_interval(request.interval)
        result = PredictionJournalService(
            journal_repository=repository,
            market_data_repository=repository,
        ).settle_predictions(
            symbol=request.symbol,
            interval=request.interval,
            until=until,
            limit=request.limit,
        )
        return jsonable_encoder({"status": "ok", **result})

    @app.post("/api/prediction-journal/summary")
    def prediction_journal_summary(request: JournalSummaryRequest) -> object:
        repository = build_repository()
        summary = PredictionJournalService(
            journal_repository=repository,
            market_data_repository=repository,
        ).summarize(
            symbol=request.symbol,
            interval=request.interval,
            start_time=parse_datetime(request.start),
            end_time=parse_datetime(request.end),
            model_name=request.model_name,
        )
        return jsonable_encoder({"status": "ok", "summary": summary.to_dict()})

    @app.get("/api/dashboard/summary")
    def dashboard_summary(
        service: DashboardServiceDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
        interval: str = Query(default="1m", min_length=1),
        limit: int = Query(default=20, ge=1, le=500),
        lookback_hours: int = Query(default=24, ge=1, le=24 * 30),
        include_prompts: bool = Query(default=False),
        include_spot_demo: bool = Query(default=False),
    ) -> object:
        return jsonable_encoder(
            service.summary(
                DashboardReportRequest(
                    symbol=symbol,
                    interval=interval,
                    limit=limit,
                    lookback_hours=lookback_hours,
                    include_prompts=include_prompts,
                    include_spot_demo=include_spot_demo,
                )
            )
        )

    @app.get("/api/agent/decisions")
    def agent_decisions(
        service: DashboardServiceDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
        interval: str = Query(default="1m", min_length=1),
        limit: int = Query(default=50, ge=1, le=500),
        include_prompts: bool = Query(default=False),
    ) -> object:
        return jsonable_encoder(
            service.decisions(symbol=symbol, interval=interval, limit=limit, include_prompts=include_prompts)
        )

    @app.get("/api/predictions")
    def predictions(
        service: DashboardServiceDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
        interval: str = Query(default="1m", min_length=1),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> object:
        return jsonable_encoder(service.predictions(symbol=symbol, interval=interval, limit=limit))

    @app.get("/api/positions")
    def positions(
        service: DashboardServiceDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
        interval: str = Query(default="1m", min_length=1),
    ) -> object:
        return jsonable_encoder(service.position(symbol=symbol, interval=interval))

    @app.get("/api/risk/status")
    def risk_status(
        service: DashboardServiceDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
    ) -> object:
        return jsonable_encoder(service.risk(symbol=symbol))

    @app.get("/api/llm/prompts/{journal_id}")
    def llm_prompt(service: DashboardServiceDependency, journal_id: int) -> object:
        payload = service.prompt(journal_id=journal_id)
        if payload["status"] == "not_found":
            raise HTTPException(status_code=404, detail=f"Agent decision journal entry {journal_id} was not found.")
        return jsonable_encoder(payload)

    @app.post("/api/agent/run-once")
    def agent_run_once(request: AgentRunOnceRequest) -> object:
        if request.policy == "threshold" and not request.symbol:
            raise HTTPException(status_code=400, detail="Threshold policy requires symbol.")
        repository = build_repository()
        portfolio = PortfolioSnapshot(
            available_usdt=request.dry_run_usdt_balance,
            base_asset_free=request.dry_run_base_asset_balance,
        )
        risk_config = _risk_config_from_args(_risk_args_from_request(request))
        exchange_adapter = None
        if request.mode == "spot-demo":
            exchange_adapter = BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))
        service = TradingAgentService(repository=repository, exchange_adapter=exchange_adapter)
        try:
            if request.policy == "llm":
                llm_policy = LLMDecisionPolicy(LLMSettings.from_env())
                try:
                    entries = service.run_llm_once(
                        interval=request.interval,
                        mode=request.mode,
                        portfolio=portfolio,
                        risk_config=risk_config,
                        llm_policy=llm_policy,
                    )
                finally:
                    llm_policy.close()
            else:
                entries = (
                    service.run_once(
                        symbol=str(request.symbol),
                        interval=request.interval,
                        mode=request.mode,
                        portfolio=portfolio,
                        risk_config=risk_config,
                    ),
                )
            payload = {"status": "ok", "decisions": [_agent_decision_payload(entry) for entry in entries]}
            if request.show_prompt:
                if request.policy != "llm":
                    raise HTTPException(status_code=400, detail="show_prompt requires policy=llm.")
                batch = service.last_llm_batch
                if batch is None:
                    raise HTTPException(status_code=500, detail="LLM prompt metadata was not produced.")
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
            return jsonable_encoder(payload)
        finally:
            if exchange_adapter is not None:
                exchange_adapter.close()

    @app.post("/api/agent/journal/summary")
    def agent_journal_summary(request: JournalSummaryRequest) -> object:
        repository = build_repository()
        summary = repository.summarize_agent_decision_journal(
            symbol=request.symbol,
            interval=request.interval,
            start_time=parse_datetime(request.start),
            end_time=parse_datetime(request.end),
        )
        return jsonable_encoder({"status": "ok", "summary": summary.to_dict()})

    @app.get("/api/spot-demo/portfolio")
    def spot_demo_portfolio(
        adapter: SpotDemoAdapterDependency,
        symbol: str = Query(default="BTCUSDT", min_length=1),
    ) -> object:
        try:
            portfolio = adapter.get_portfolio(symbol)
            return jsonable_encoder({"status": "ok", "symbol": symbol, "portfolio": portfolio.to_dict()})
        finally:
            adapter.close()

    @app.post("/api/spot-demo/market-buy")
    def spot_demo_market_buy(adapter: SpotDemoAdapterDependency, request: SpotDemoMarketBuyRequest) -> object:
        if not request.confirm:
            raise HTTPException(status_code=400, detail="Manual Spot Demo market buy requires confirm=true.")
        try:
            before = adapter.get_portfolio(request.symbol)
            order = adapter.submit_market_order(
                request.symbol,
                ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=request.usdt_amount),
            )
            after = adapter.get_portfolio(request.symbol)
            return jsonable_encoder(
                {
                    "status": "ok",
                    "symbol": request.symbol,
                    "usdt_amount": request.usdt_amount,
                    "portfolio_before": before.to_dict(),
                    "order": order,
                    "portfolio_after": after.to_dict(),
                }
            )
        finally:
            adapter.close()

    @app.post("/api/spot-demo/market-sell")
    def spot_demo_market_sell(adapter: SpotDemoAdapterDependency, request: SpotDemoMarketSellRequest) -> object:
        if not request.confirm:
            raise HTTPException(status_code=400, detail="Manual Spot Demo market sell requires confirm=true.")
        try:
            before = adapter.get_portfolio(request.symbol)
            order = adapter.submit_market_order(
                request.symbol,
                ProposedDecision(action=DecisionAction.SELL, requested_quantity=request.quantity),
            )
            after = adapter.get_portfolio(request.symbol)
            return jsonable_encoder(
                {
                    "status": "ok",
                    "symbol": request.symbol,
                    "quantity": request.quantity,
                    "portfolio_before": before.to_dict(),
                    "order": order,
                    "portfolio_after": after.to_dict(),
                }
            )
        finally:
            adapter.close()

    @app.post("/api/agent/run-live-once")
    def agent_run_live_once(request: LiveCycleRunOnceRequest) -> object:
        args = SimpleNamespace(
            interval=request.interval,
            mode=request.mode,
            model_artifact=request.model_artifacts,
            market_data_mode=request.market_data_mode,
            max_inline_gap_minutes=request.max_inline_gap_minutes,
            max_model_age_days=request.max_model_age_days,
            allow_large_gap_recovery=request.allow_large_gap_recovery,
            allow_stale_models=request.allow_stale_models,
            max_trade_usdt=request.max_trade_usdt,
            max_position_usdt=request.max_position_usdt,
            emergency_stop=request.emergency_stop,
            max_daily_realized_loss_usdt=request.max_daily_realized_loss_usdt,
            max_orders_per_day=request.max_orders_per_day,
            order_cooldown_minutes=request.order_cooldown_minutes,
            max_total_exposure_usdt=request.max_total_exposure_usdt,
        )
        service, market_data_adapter, exchange_adapter, llm_policy = _build_live_cycle_service(args)
        try:
            return jsonable_encoder(_live_cycle_payload(service.run_once(interval=request.interval, mode=request.mode)))
        finally:
            llm_policy.close()
            market_data_adapter.close()
            if exchange_adapter is not None:
                exchange_adapter.close()

    return app


app = create_app()


def main() -> None:
    """Run the API with uvicorn."""
    parser = argparse.ArgumentParser(description="Run the CAPM dashboard API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    uvicorn.run("capm.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
