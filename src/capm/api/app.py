"""FastAPI application for CAPM dashboard reads."""

from __future__ import annotations

import argparse
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from capm.main import build_repository
from capm.services.dashboard import DashboardReportRequest, DashboardReportService


def get_dashboard_service() -> DashboardReportService:
    """Build the dashboard service from environment-backed repository settings."""
    return DashboardReportService(build_repository())


DashboardServiceDependency = Annotated[DashboardReportService, Depends(get_dashboard_service)]


def create_app() -> FastAPI:
    """Create the dashboard API application."""
    app = FastAPI(title="CAPM Dashboard API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["GET"],
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
