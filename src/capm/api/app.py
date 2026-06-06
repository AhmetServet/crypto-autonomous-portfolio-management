"""FastAPI application for CAPM dashboard reads."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from capm.core.config import BinanceSettings
from capm.domains.trading import DecisionAction, ProposedDecision
from capm.infra.exchange import BinanceSpotDemoTradingAdapter
from capm.main import _build_live_cycle_service, _live_cycle_payload, build_repository
from capm.services.dashboard import DashboardReportRequest, DashboardReportService


def get_dashboard_service() -> DashboardReportService:
    """Build the dashboard service from environment-backed repository settings."""
    return DashboardReportService(build_repository())


def get_spot_demo_adapter() -> BinanceSpotDemoTradingAdapter:
    """Build an authenticated Spot Demo trading adapter."""
    return BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))


DashboardServiceDependency = Annotated[DashboardReportService, Depends(get_dashboard_service)]
SpotDemoAdapterDependency = Annotated[BinanceSpotDemoTradingAdapter, Depends(get_spot_demo_adapter)]


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
