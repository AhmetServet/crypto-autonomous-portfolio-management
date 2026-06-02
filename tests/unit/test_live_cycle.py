"""Unit tests for one closed-candle live trading cycle."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from capm.domains.market_data import OHLCV
from capm.services.ingestion import IngestionResult
from capm.services.live_cycle import LiveTradingCycleService


def _candle(minute: int) -> OHLCV:
    open_time = datetime(2026, 6, 2, 12, minute, tzinfo=UTC)
    return OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=Decimal("1"),
        quote_asset_volume=Decimal("100"),
        trade_count=1,
        taker_buy_base_asset_volume=Decimal("1"),
        taker_buy_quote_asset_volume=Decimal("100"),
    )


class Repository:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.latest = _candle(3).open_time
        self.candles = [_candle(minute) for minute in range(5)]

    @contextmanager
    def cycle_lock(self, lock_key):
        yield self.acquired

    def get_available_symbols(self, interval):
        return ("BTCUSDT",)

    def get_latest_candle_time(self, symbol, interval):
        return self.latest

    def get_candles(self, symbol, interval, start_time, end_time):
        return [candle for candle in self.candles if start_time <= candle.open_time < end_time]

    def save_indicator_batch(self, indicators):
        return None


class LiveCycleTests(unittest.TestCase):
    def test_cycle_skips_when_advisory_lock_is_not_acquired(self) -> None:
        result = LiveTradingCycleService(
            repository=Repository(acquired=False),
            market_data_adapter=object(),
            trading_agent=object(),
            llm_policy=object(),
            artifacts_by_symbol={"BTCUSDT": (Path("/tmp/model.pkl"),)},
            now=lambda: datetime(2026, 6, 2, 12, 5, 30, tzinfo=UTC),
            allow_stale_models=True,
        ).run_once()

        self.assertEqual(result.skipped_reason, "cycle_lock_not_acquired")

    def test_cycle_ingests_to_last_closed_candle_then_predicts_and_runs_llm(self) -> None:
        repository = Repository()
        calls = []

        class Ingestion:
            def __init__(self, **kwargs):
                pass

            def ingest_ohlcv(self, request):
                calls.append(("ingest", request.start_at, request.end_at))
                repository.latest = _candle(4).open_time
                return IngestionResult(
                    fetched_count=1,
                    stored_count=1,
                    started_at=request.start_at,
                    ended_at=request.end_at,
                )

        class Journal:
            def __init__(self, **kwargs):
                pass

            def settle_predictions(self, **kwargs):
                calls.append(("settle", kwargs["until"]))
                return {"settled": 2}

        class TradingAgent:
            def run_llm_once(self, **kwargs):
                calls.append(("llm", kwargs["interval"], kwargs["mode"]))
                return ("decision",)

        with (
            patch("capm.services.live_cycle.HistoricalMarketDataIngestionService", Ingestion),
            patch("capm.services.live_cycle.PredictionJournalService", Journal),
        ):
            result = LiveTradingCycleService(
                repository=repository,
                market_data_adapter=object(),
                trading_agent=TradingAgent(),
                llm_policy=object(),
                artifacts_by_symbol={"BTCUSDT": (Path("/tmp/xgboost.pkl"), Path("/tmp/lstm.pkl"))},
                now=lambda: datetime(2026, 6, 2, 12, 5, 30, tzinfo=UTC),
                allow_stale_models=True,
                prediction_runner=lambda path, symbol, interval, reference_time: calls.append(
                    ("predict", path, reference_time)
                ),
            ).run_once(mode="spot-demo")

        self.assertEqual(result.cycle_time, datetime(2026, 6, 2, 12, 5, tzinfo=UTC))
        self.assertEqual(result.ingested_candles, 1)
        self.assertEqual(result.predictions_journaled, 2)
        self.assertEqual(result.predictions_settled, 2)
        self.assertEqual(result.decisions, ("decision",))
        self.assertIn(("ingest", _candle(4).open_time, datetime(2026, 6, 2, 12, 5, tzinfo=UTC)), calls)
        self.assertIn(("llm", "1m", "spot-demo"), calls)

    def test_cycle_rejects_symbols_without_configured_artifacts(self) -> None:
        with self.assertRaisesRegex(ValueError, "No production model artifacts configured"):
            LiveTradingCycleService(
                repository=Repository(),
                market_data_adapter=object(),
                trading_agent=object(),
                llm_policy=object(),
                artifacts_by_symbol={},
                now=lambda: datetime(2026, 6, 2, 12, 5, tzinfo=UTC),
            ).run_once()

    def test_cycle_rejects_stale_model_artifact_before_ingestion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "model.pkl"
            artifact.touch()
            stale_time = datetime(2026, 5, 20, tzinfo=UTC).timestamp()
            os.utime(artifact, (stale_time, stale_time))

            with self.assertRaisesRegex(ValueError, "Train fresh production models first"):
                LiveTradingCycleService(
                    repository=Repository(),
                    market_data_adapter=object(),
                    trading_agent=object(),
                    llm_policy=object(),
                    artifacts_by_symbol={"BTCUSDT": (artifact,)},
                    now=lambda: datetime(2026, 6, 2, 12, 5, tzinfo=UTC),
                ).run_once()

    def test_cycle_rejects_large_inline_gap_without_explicit_recovery(self) -> None:
        repository = Repository()
        repository.latest = datetime(2026, 6, 2, 2, 0, tzinfo=UTC)

        with self.assertRaisesRegex(ValueError, "allow-large-gap-recovery"):
            LiveTradingCycleService(
                repository=repository,
                market_data_adapter=object(),
                trading_agent=object(),
                llm_policy=object(),
                artifacts_by_symbol={"BTCUSDT": (Path("/tmp/model.pkl"),)},
                now=lambda: datetime(2026, 6, 2, 12, 5, tzinfo=UTC),
                allow_stale_models=True,
            ).run_once()

    def test_prediction_worker_is_invoked_in_isolated_process(self) -> None:
        service = LiveTradingCycleService(
            repository=Repository(),
            market_data_adapter=object(),
            trading_agent=object(),
            llm_policy=object(),
            artifacts_by_symbol={},
        )

        with patch("capm.services.live_cycle.subprocess.run") as run:
            service._journal_prediction(
                Path("/tmp/model.pkl"),
                "BTCUSDT",
                "1m",
                datetime(2026, 6, 2, 12, 4, tzinfo=UTC),
            )

        command = run.call_args.args[0]
        self.assertIn("capm.predict_worker", command)
        self.assertEqual(run.call_args.kwargs["check"], True)


if __name__ == "__main__":
    unittest.main()
