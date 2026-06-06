"""Unit tests for explicit Spot Demo CLI safety checks."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from capm.domains.features import ComputedIndicatorSet
from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionJournalEntry, PredictionJournalSummary
from capm.domains.trading import AgentDecisionJournalEntry, AgentDecisionJournalSummary, OperationalRiskSnapshot

main_module = importlib.import_module("capm.main")


class MainCLITests(unittest.TestCase):
    """Exercise parser-level Spot Demo smoke-test safeguards."""

    def test_parse_model_artifacts_groups_repeated_symbol_paths(self) -> None:
        parsed = main_module._parse_model_artifacts(["btcusdt=/tmp/xgboost.pkl", "BTCUSDT=/tmp/lstm.pkl"])

        self.assertEqual(
            parsed["BTCUSDT"],
            (Path("/tmp/xgboost.pkl"), Path("/tmp/lstm.pkl")),
        )

    def test_parse_model_artifacts_requires_symbol_path_mapping(self) -> None:
        with self.assertRaisesRegex(ValueError, "SYMBOL=PATH"):
            main_module._parse_model_artifacts(["/tmp/model.pkl"])

    def test_test_market_buy_requires_confirm_before_adapter_creation(self) -> None:
        with patch(
            "sys.argv",
            ["capm", "spot-demo", "test-market-buy", "--symbol", "BTCUSDT", "--usdt-amount", "10"],
        ):
            with patch("capm.main.BinanceSpotDemoTradingAdapter") as adapter:
                with self.assertRaises(SystemExit):
                    main_module.main()
        adapter.assert_not_called()

    def test_test_market_buy_rejects_non_positive_amount(self) -> None:
        with patch(
            "sys.argv",
            ["capm", "spot-demo", "test-market-buy", "--symbol", "BTCUSDT", "--usdt-amount", "0", "--confirm"],
        ):
            with patch("capm.main.BinanceSpotDemoTradingAdapter") as adapter:
                with self.assertRaises(SystemExit):
                    main_module.main()
        adapter.assert_not_called()

    def test_seconds_until_next_cycle_aligns_after_candle_close(self) -> None:
        seconds = main_module._seconds_until_next_cycle(
            interval="1m",
            offset_seconds=2,
            now=datetime(2026, 6, 5, 12, 0, 30, tzinfo=UTC),
        )

        self.assertEqual(seconds, 32)

    def test_run_live_loop_stops_after_max_cycles(self) -> None:
        class Service:
            def __init__(self):
                self.calls = 0

            def run_once(self, **kwargs):
                self.calls += 1
                return SimpleNamespace(
                    cycle_time=datetime(2026, 6, 5, 12, self.calls, tzinfo=UTC),
                    symbols=("BTCUSDT",),
                    ingested_candles=0,
                    persisted_indicators=0,
                    predictions_journaled=0,
                    predictions_settled=0,
                    skipped_reason=None,
                    decisions=(),
                )

        service = Service()
        closes = []
        args = SimpleNamespace(
            interval="1m",
            mode="dry-run",
            max_cycles=2,
            cycle_offset_seconds=0,
            stop_after_error_count=3,
            sleep_after_error_seconds=0,
        )
        with patch("capm.main._build_live_cycle_service", return_value=(service, SimpleNamespace(close=lambda: closes.append("market")), None, SimpleNamespace(close=lambda: closes.append("llm")))):
            with patch("capm.main.print_json"):
                main_module._run_live_loop(
                    args,
                    sleep=lambda seconds: None,
                    now=lambda: datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
                )

        self.assertEqual(service.calls, 2)
        self.assertEqual(closes, ["llm", "market"])

    def test_run_live_loop_retries_until_error_limit(self) -> None:
        class Service:
            def run_once(self, **kwargs):
                raise ValueError("temporary failure")

        args = SimpleNamespace(
            interval="1m",
            mode="dry-run",
            max_cycles=2,
            cycle_offset_seconds=0,
            stop_after_error_count=2,
            sleep_after_error_seconds=0,
        )
        with patch("capm.main._build_live_cycle_service", return_value=(Service(), SimpleNamespace(close=lambda: None), None, SimpleNamespace(close=lambda: None))):
            with patch("capm.main.print_json"):
                with self.assertRaises(SystemExit) as context:
                    main_module._run_live_loop(
                        args,
                        sleep=lambda seconds: None,
                        now=lambda: datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
                    )
        self.assertEqual(context.exception.code, 1)

    def test_run_live_loop_counts_failed_attempts_toward_max_cycles(self) -> None:
        class Service:
            def __init__(self):
                self.calls = 0

            def run_once(self, **kwargs):
                self.calls += 1
                raise ValueError("temporary failure")

        service = Service()
        args = SimpleNamespace(
            interval="1m",
            mode="dry-run",
            max_cycles=1,
            cycle_offset_seconds=0,
            stop_after_error_count=3,
            sleep_after_error_seconds=0,
        )
        with patch("capm.main._build_live_cycle_service", return_value=(service, SimpleNamespace(close=lambda: None), None, SimpleNamespace(close=lambda: None))):
            with patch("capm.main.print_json"):
                with self.assertRaises(SystemExit) as context:
                    main_module._run_live_loop(
                        args,
                        sleep=lambda seconds: None,
                        now=lambda: datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
                    )
        self.assertEqual(service.calls, 1)
        self.assertEqual(context.exception.code, 1)

    def test_agent_report_rejects_invalid_limit(self) -> None:
        with patch("sys.argv", ["capm", "agent", "report", "--symbol", "BTCUSDT", "--limit", "0"]):
            with self.assertRaises(SystemExit):
                main_module.main()

    def test_agent_report_builds_recent_state_payload(self) -> None:
        class Repository:
            def get_latest_candle_time(self, symbol, interval):
                return datetime(2024, 1, 1, 0, 0, tzinfo=UTC)

            def get_candle(self, symbol, interval, open_time):
                return OHLCV(
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    close_time=datetime(2024, 1, 1, 0, 0, 59, tzinfo=UTC),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.5"),
                    volume=Decimal("10"),
                    quote_asset_volume=Decimal("1000"),
                    trade_count=5,
                    taker_buy_base_asset_volume=Decimal("4"),
                    taker_buy_quote_asset_volume=Decimal("400"),
                )

            def get_latest_indicator_time(self, symbol, interval):
                return datetime(2024, 1, 1, 0, 0, tzinfo=UTC)

            def get_indicator_set(self, symbol, interval, open_time):
                return ComputedIndicatorSet(
                    symbol=symbol,
                    interval=interval,
                    open_time=open_time,
                    values={"rsi_14_close": Decimal("55.5")},
                    is_ready=True,
                    missing_outputs=(),
                )

            def list_recent_prediction_journal_entries(self, symbol, interval, limit):
                return (
                    PredictionJournalEntry(
                        id=1,
                        created_at=None,
                        updated_at=None,
                        symbol=symbol,
                        interval=interval,
                        model_name="xgboost",
                        artifact_kind="production_tabular",
                        artifact_path="experiments/results/run/model.pkl",
                        artifact_sha256="a" * 64,
                        reference_time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                        prediction_time=datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
                        forecast_horizon=15,
                        target_field="close",
                        target_mode="return",
                        reference_value=100.0,
                        predicted_value=101.0,
                        predicted_return=0.01,
                        predicted_direction="up",
                        feature_names=("rsi_14_close",),
                        metadata={},
                    ),
                )

            def list_recent_agent_decision_journal_entries(self, symbol, interval, limit):
                return (
                    AgentDecisionJournalEntry(
                        id=2,
                        created_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                        updated_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                        cycle_id="cycle-1",
                        mode="dry-run",
                        symbol=symbol,
                        interval=interval,
                        reference_time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                        action="buy",
                        requested_usdt_amount=25.0,
                        confidence=0.7,
                        reason="test",
                        risk_status="approved",
                        execution_status="not_submitted",
                        metadata={"llm_model": "test-model"},
                    ),
                )

            def summarize_prediction_journal(self, symbol, interval, start_time, end_time, model_name=None):
                return PredictionJournalSummary(
                    symbol=symbol,
                    interval=interval,
                    model_name=model_name,
                    start_time=start_time,
                    end_time=end_time,
                    prediction_count=1,
                    settled_count=0,
                    mape=None,
                    rmse=None,
                    direction_accuracy=None,
                    mean_predicted_return=0.01,
                    mean_actual_return=None,
                    predicted_direction_counts={"up": 1, "down": 0, "flat": 0},
                    actual_direction_counts={"up": 0, "down": 0, "flat": 0},
                )

            def summarize_agent_decision_journal(self, symbol, interval, start_time, end_time):
                return AgentDecisionJournalSummary(
                    symbol=symbol,
                    interval=interval,
                    start_time=start_time,
                    end_time=end_time,
                    decision_count=1,
                    action_counts={"buy": 1, "sell": 0, "hold": 0},
                    risk_status_counts={"approved": 1, "rejected": 0, "skipped": 0},
                    execution_status_counts={"not_submitted": 1},
                    mode_counts={"dry_run": 1, "spot_demo": 0},
                )

            def get_operational_risk_snapshot(self, symbol, at):
                return OperationalRiskSnapshot(
                    orders_today=0,
                    realized_pnl_today_usdt=0.0,
                    observed_at=at,
                    position_quantity=0.1,
                    position_cost_usdt=9.5,
                )

        args = SimpleNamespace(
            symbol="BTCUSDT",
            interval="1m",
            limit=5,
            lookback_hours=24.0,
            include_spot_demo=False,
            include_prompts=False,
        )
        with patch("capm.main.build_repository", return_value=Repository()):
            payload = main_module._agent_report_payload(args)

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["market"]["latest_candle"]["close"], "100.5")
        self.assertEqual(payload["position"]["status"], "long")
        self.assertEqual(payload["position"]["current_exposure_usdt"], 10.05)
        self.assertAlmostEqual(payload["position"]["unrealized_pnl_usdt"], 0.55)
        self.assertEqual(len(payload["recent_predictions"]), 1)
        self.assertEqual(payload["recent_decisions"][0]["llm"]["model"], "test-model")


if __name__ == "__main__":
    unittest.main()
