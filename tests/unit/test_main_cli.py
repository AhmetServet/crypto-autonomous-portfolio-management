"""Unit tests for explicit Spot Demo CLI safety checks."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
