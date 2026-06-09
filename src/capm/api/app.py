"""FastAPI application for CAPM dashboard reads."""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .dependencies import get_dashboard_service, get_spot_demo_adapter
from .routers.dashboard import router as dashboard_router
from .routers.market import router as market_router
from .routers.predictions import router as predictions_router
from .routers.trading import router as trading_router
from .routers.training import router as training_router


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
    app.include_router(dashboard_router)
    app.include_router(training_router)
    app.include_router(market_router)
    app.include_router(predictions_router)
    app.include_router(trading_router)
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
