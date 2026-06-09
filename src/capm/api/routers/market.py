"""Database and market-data routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder

from capm.core.config import BinanceSettings
from capm.domains.market_data import HistoricalOHLCRequest, interval_to_timedelta
from capm.infra.exchange import BinanceSpotMarketDataAdapter
from capm.init_db import initialize_database
from capm.main import build_repository, fetch_ohlcv, parse_datetime
from capm.services.features import IndicatorPipelineService
from capm.services.ingestion import BinancePublicDumpIngestionService, HistoricalMarketDataIngestionService
from capm.services.live_cycle import default_live_indicator_specs

from ..schemas import BackfillIndicatorsRequest, FetchOHLCVRequest, IngestOHLCVRequest, InitDatabaseRequest, RepairOHLCVGapsRequest
from ..shared import coverage_range_payload, time_range_payload

router = APIRouter()


@router.post("/api/database/init")
def init_database(request: InitDatabaseRequest) -> object:
    repository = initialize_database(request.symbols)
    return jsonable_encoder(
        {
            "status": "ok",
            "database": repository._engine.url.database or "configured database",
            "symbols": request.symbols,
        }
    )


@router.post("/api/market/fetch-ohlcv")
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


@router.post("/api/market/ingest-ohlcv")
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
        result = service.ingest_ohlcv(ohlcv_request, include_rest_tail=request.source == "dump-with-rest-tail")
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


@router.get("/api/data/coverage")
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
                "covered_ranges": [coverage_range_payload(item) for item in ohlcv_plan.covered_ranges],
                "missing_ranges": [time_range_payload(item) for item in ohlcv_plan.missing_ranges],
            },
            "indicators": {
                "covered_ranges": [coverage_range_payload(item) for item in indicator_ranges],
                "missing_ranges": [time_range_payload(item) for item in indicator_missing],
            },
            "features": {
                "covered_ranges": [coverage_range_payload(item) for item in feature_ranges],
                "missing_ranges": [time_range_payload(item) for item in feature_missing],
            },
        }
    )


@router.post("/api/market/repair-ohlcv-gaps")
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


@router.post("/api/features/backfill-indicators")
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
