"""Unit tests for the dashboard API route layer."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from capm.api.app import create_app, get_dashboard_service


class FakeDashboardService:
    """Small route-test double for dashboard service calls."""

    def health(self):
        return {"status": "ok", "database": "reachable"}

    def list_symbols(self, *, interval: str):
        return {"status": "ok", "interval": interval, "symbols": ("BTCUSDT",)}

    def summary(self, request):
        return {
            "status": "ok",
            "symbol": request.symbol,
            "interval": request.interval,
            "recent_predictions": [],
            "recent_decisions": [],
        }

    def decisions(self, *, symbol: str, interval: str, limit: int, include_prompts: bool = False):
        return {
            "status": "ok",
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "include_prompts": include_prompts,
            "decisions": [],
        }

    def predictions(self, *, symbol: str, interval: str, limit: int):
        return {"status": "ok", "symbol": symbol, "interval": interval, "limit": limit, "predictions": []}

    def position(self, *, symbol: str, interval: str):
        return {"status": "ok", "symbol": symbol, "interval": interval, "position": {"status": "flat"}}

    def risk(self, *, symbol: str):
        return {"status": "ok", "symbol": symbol, "operational_risk": {"orders_today": 0}}

    def prompt(self, *, journal_id: int):
        if journal_id == 404:
            return {"status": "not_found", "journal_id": journal_id}
        return {"status": "ok", "journal_id": journal_id, "prompt": "user prompt"}


class DashboardApiTests(unittest.TestCase):
    """Exercise GET routes for the React dashboard backend."""

    def setUp(self) -> None:
        self.app = create_app()
        self.app.dependency_overrides[get_dashboard_service] = FakeDashboardService
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def test_health_route(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_summary_route_passes_query_parameters(self) -> None:
        response = self.client.get("/api/dashboard/summary?symbol=ETHUSDT&interval=5m&limit=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["symbol"], "ETHUSDT")
        self.assertEqual(response.json()["interval"], "5m")

    def test_read_only_dashboard_routes(self) -> None:
        paths = (
            "/api/symbols?interval=1m",
            "/api/agent/decisions?symbol=BTCUSDT&interval=1m&limit=10&include_prompts=true",
            "/api/predictions?symbol=BTCUSDT&interval=1m&limit=10",
            "/api/positions?symbol=BTCUSDT&interval=1m",
            "/api/risk/status?symbol=BTCUSDT",
            "/api/llm/prompts/1",
        )

        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "ok")

    def test_prompt_route_returns_404_for_missing_journal_entry(self) -> None:
        response = self.client.get("/api/llm/prompts/404")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
