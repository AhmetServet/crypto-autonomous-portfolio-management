"""Read-only dashboard routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from capm.services.dashboard import DashboardReportRequest

from ..dependencies import DashboardServiceDependency

router = APIRouter()


@router.get("/api/health")
def health(service: DashboardServiceDependency) -> object:
    return jsonable_encoder(service.health())


@router.get("/api/symbols")
def symbols(service: DashboardServiceDependency, interval: str = Query(default="1m", min_length=1)) -> object:
    return jsonable_encoder(service.list_symbols(interval=interval))


@router.get("/api/dashboard/summary")
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


@router.get("/api/charts/dashboard")
def dashboard_charts(
    service: DashboardServiceDependency,
    symbol: str = Query(default="BTCUSDT", min_length=1),
    interval: str = Query(default="1m", min_length=1),
    lookback_hours: int = Query(default=24, ge=1, le=24 * 30),
    limit: int = Query(default=500, ge=10, le=5000),
) -> object:
    return jsonable_encoder(
        service.charts(symbol=symbol, interval=interval, lookback_hours=lookback_hours, limit=limit)
    )


@router.get("/api/agent/decisions")
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


@router.get("/api/execution/orders")
def execution_orders(
    service: DashboardServiceDependency,
    symbol: str = Query(default="BTCUSDT", min_length=1),
    interval: str = Query(default="1m", min_length=1),
    limit: int = Query(default=50, ge=1, le=500),
) -> object:
    return jsonable_encoder(service.orders(symbol=symbol, interval=interval, limit=limit))


@router.get("/api/predictions")
def predictions(
    service: DashboardServiceDependency,
    symbol: str = Query(default="BTCUSDT", min_length=1),
    interval: str = Query(default="1m", min_length=1),
    limit: int = Query(default=100, ge=1, le=1000),
) -> object:
    return jsonable_encoder(service.predictions(symbol=symbol, interval=interval, limit=limit))


@router.get("/api/positions")
def positions(
    service: DashboardServiceDependency,
    symbol: str = Query(default="BTCUSDT", min_length=1),
    interval: str = Query(default="1m", min_length=1),
) -> object:
    return jsonable_encoder(service.position(symbol=symbol, interval=interval))


@router.get("/api/risk/status")
def risk_status(service: DashboardServiceDependency, symbol: str = Query(default="BTCUSDT", min_length=1)) -> object:
    return jsonable_encoder(service.risk(symbol=symbol))


@router.get("/api/llm/prompts/{journal_id}")
def llm_prompt(service: DashboardServiceDependency, journal_id: int) -> object:
    payload = service.prompt(journal_id=journal_id)
    if payload["status"] == "not_found":
        raise HTTPException(status_code=404, detail=f"Agent decision journal entry {journal_id} was not found.")
    return jsonable_encoder(payload)
