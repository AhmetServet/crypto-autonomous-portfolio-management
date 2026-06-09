"""Dependency builders for the dashboard API."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from capm.core.config import BinanceSettings
from capm.infra.exchange import BinanceSpotDemoTradingAdapter
from capm.main import build_repository
from capm.services.dashboard import DashboardReportService


def get_dashboard_service() -> DashboardReportService:
    """Build the dashboard service from environment-backed repository settings."""
    return DashboardReportService(build_repository())


def get_spot_demo_adapter() -> BinanceSpotDemoTradingAdapter:
    """Build an authenticated Spot Demo trading adapter."""
    return BinanceSpotDemoTradingAdapter(BinanceSettings.from_env(mode="demo"))


DashboardServiceDependency = Annotated[DashboardReportService, Depends(get_dashboard_service)]
SpotDemoAdapterDependency = Annotated[BinanceSpotDemoTradingAdapter, Depends(get_spot_demo_adapter)]
