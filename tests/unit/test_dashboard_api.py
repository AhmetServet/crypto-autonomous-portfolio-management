"""Unit tests for the dashboard API route layer."""

from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from capm.api.app import create_app, get_dashboard_service, get_spot_demo_adapter
from capm.domains.trading import PortfolioSnapshot


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


class FakeRepository:
    """Small repository double for operation-route tests."""

    _engine = SimpleNamespace(url=SimpleNamespace(database="test-db"))

    def summarize_agent_decision_journal(self, **kwargs):
        return SimpleNamespace(to_dict=lambda: {"decision_count": 0, **kwargs})


class FakeSpotDemoAdapter:
    """Route-test double for Spot Demo account and order calls."""

    def __init__(self) -> None:
        self.closed = False
        self.orders = []

    def get_portfolio(self, symbol: str):
        return PortfolioSnapshot(available_usdt=100.0, base_asset_free=0.01)

    def submit_market_order(self, symbol: str, decision):
        self.orders.append((symbol, decision))
        return {"symbol": symbol, "side": decision.action.value.upper(), "status": "FILLED"}

    def close(self):
        self.closed = True


class FakeLivePolicy:
    def close(self):
        pass


class FakeClosable:
    def close(self):
        pass


class FakeLiveCycle:
    def run_once(self, *, interval: str, mode: str):
        return type(
            "Result",
            (),
            {
                "cycle_time": datetime(2026, 6, 7, 12, 0, tzinfo=UTC),
                "symbols": ("BTCUSDT",),
                "ingested_candles": 0,
                "persisted_indicators": 0,
                "predictions_journaled": 0,
                "predictions_settled": 0,
                "decisions": (),
                "skipped_reason": None,
            },
        )()


class DashboardApiTests(unittest.TestCase):
    """Exercise GET routes for the React dashboard backend."""

    def setUp(self) -> None:
        self.app = create_app()
        self.app.dependency_overrides[get_dashboard_service] = FakeDashboardService
        self.app.dependency_overrides[get_spot_demo_adapter] = FakeSpotDemoAdapter
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

    def test_spot_demo_portfolio_route(self) -> None:
        response = self.client.get("/api/spot-demo/portfolio?symbol=BTCUSDT")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["portfolio"]["available_usdt"], 100.0)

    def test_manual_spot_demo_order_routes_require_confirmation(self) -> None:
        response = self.client.post(
            "/api/spot-demo/market-buy",
            json={"symbol": "BTCUSDT", "usdt_amount": 10, "confirm": False},
        )

        self.assertEqual(response.status_code, 400)

    def test_manual_spot_demo_order_routes_submit_confirmed_orders(self) -> None:
        buy_response = self.client.post(
            "/api/spot-demo/market-buy",
            json={"symbol": "BTCUSDT", "usdt_amount": 10, "confirm": True},
        )
        sell_response = self.client.post(
            "/api/spot-demo/market-sell",
            json={"symbol": "BTCUSDT", "quantity": 0.001, "confirm": True},
        )

        self.assertEqual(buy_response.status_code, 200)
        self.assertEqual(buy_response.json()["order"]["side"], "BUY")
        self.assertEqual(sell_response.status_code, 200)
        self.assertEqual(sell_response.json()["order"]["side"], "SELL")

    def test_agent_run_live_once_route_returns_cycle_payload(self) -> None:
        with patch(
            "capm.api.app._build_live_cycle_service",
            return_value=(FakeLiveCycle(), FakeClosable(), None, FakeLivePolicy()),
        ):
            response = self.client.post(
                "/api/agent/run-live-once",
                json={
                    "interval": "1m",
                    "mode": "dry-run",
                    "model_artifacts": ["BTCUSDT=experiments/results/run/model.pkl"],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["symbols"], ["BTCUSDT"])

    def test_model_artifacts_route_lists_latest_trained_models(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir)
            run_dir = results_dir / "20260601T000000Z_btcusdt_1m_xgboost_prod_15steps"
            run_dir.mkdir()
            artifact = run_dir / "model.pkl"
            artifact.write_bytes(b"model")
            (run_dir / "summary.json").write_text(
                """
                {
                  "run_id": "20260601T000000Z_btcusdt_1m_xgboost_prod_15steps",
                  "symbol": "BTCUSDT",
                  "interval": "1m",
                  "model_name": "xgboost",
                  "model_artifact_path": "%s",
                  "end_time": "2026-06-01T00:00:00+00:00",
                  "metrics": {"direction_accuracy": 0.52},
                  "backtest": {"cumulative_return": 0.01, "trade_count": 2}
                }
                """
                % artifact
            )
            walk_forward_dir = results_dir / "20260602T000000Z_btcusdt_1m_arima_15h"
            walk_forward_dir.mkdir()
            walk_forward_artifact = walk_forward_dir / "trained_models.pkl"
            walk_forward_artifact.write_bytes(b"models")
            (walk_forward_dir / "summary.json").write_text(
                """
                {
                  "request": {
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "model_name": "arima",
                    "end_time": "2026-06-02T00:00:00+00:00"
                  },
                  "aggregate_metrics": {"direction_accuracy": 0.75}
                }
                """
            )

            with patch("capm.api.app.MODEL_RESULTS_DIR", results_dir):
                response = self.client.get("/api/model-artifacts?symbol=BTCUSDT&interval=1m")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["artifacts"]), 2)
        self.assertEqual({item["model_name"] for item in body["artifacts"]}, {"arima", "xgboost"})
        self.assertEqual({item["artifact_kind"] for item in body["artifacts"]}, {"production", "walk_forward"})
        self.assertIn(str(artifact), {item["artifact_path"] for item in body["latest_by_model"]})
        self.assertIn(str(walk_forward_artifact), {item["artifact_path"] for item in body["latest_by_model"]})

    def test_database_init_route_initializes_symbols(self) -> None:
        with patch("capm.api.app.initialize_database", return_value=FakeRepository()) as initialize:
            response = self.client.post("/api/database/init", json={"symbols": ["BTCUSDT"]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "test-db")
        initialize.assert_called_once_with(["BTCUSDT"])

    def test_agent_run_once_threshold_requires_symbol(self) -> None:
        response = self.client.post(
            "/api/agent/run-once",
            json={"interval": "1m", "policy": "threshold", "mode": "dry-run"},
        )

        self.assertEqual(response.status_code, 400)

    def test_agent_journal_summary_route(self) -> None:
        with patch("capm.api.app.build_repository", return_value=FakeRepository()):
            response = self.client.post(
                "/api/agent/journal/summary",
                json={
                    "symbol": "BTCUSDT",
                    "interval": "1m",
                    "start": "2026-06-01T00:00:00Z",
                    "end": "2026-06-02T00:00:00Z",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"]["decision_count"], 0)


if __name__ == "__main__":
    unittest.main()
