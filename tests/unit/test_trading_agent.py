"""Unit tests for the deterministic trading-agent dry-run slice."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionJournalEntry
from capm.domains.trading import PortfolioSnapshot, RiskConfig
from capm.services.trading_agent import TradingAgentService


def _candle() -> OHLCV:
    open_time = datetime(2024, 1, 1, tzinfo=UTC)
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


def _prediction(predicted_return: float) -> PredictionJournalEntry:
    candle = _candle()
    return PredictionJournalEntry(
        id=7,
        created_at=None,
        updated_at=None,
        symbol="BTCUSDT",
        interval="1m",
        model_name="xgboost",
        artifact_kind="production_tabular",
        artifact_path="/tmp/model.pkl",
        artifact_sha256="a" * 64,
        reference_time=candle.open_time,
        prediction_time=candle.open_time + timedelta(minutes=15),
        forecast_horizon=15,
        target_field="close",
        target_mode="return",
        reference_value=100.0,
        predicted_value=100.2,
        predicted_return=predicted_return,
        predicted_direction="up",
        feature_names=(),
        metadata={},
    )


class TradingRepository:
    """In-memory repository double for one dry-run cycle."""

    def __init__(self, predictions=()) -> None:
        self.candle = _candle()
        self.predictions = tuple(predictions)
        self.saved = []

    def get_latest_candle_time(self, symbol, interval):
        return self.candle.open_time

    def get_candle(self, symbol, interval, open_time):
        return self.candle

    def get_latest_prediction_journal_entries(self, symbol, interval, reference_time, stale_after):
        return self.predictions

    def save_agent_decision_journal_entry(self, entry):
        saved = replace(entry, id=1)
        self.saved.append(saved)
        return saved


class TradingAgentTests(unittest.TestCase):
    """Exercise deterministic policy, risk gate, and journaling."""

    def test_no_predictions_produce_journaled_hold(self) -> None:
        repository = TradingRepository()

        entry = TradingAgentService(repository=repository).run_once(symbol="BTCUSDT", interval="1m")

        self.assertEqual(entry.action, "hold")
        self.assertEqual(entry.risk_status, "skipped")
        self.assertEqual(entry.execution_status, "not_submitted")

    def test_up_prediction_produces_approved_dry_run_buy(self) -> None:
        repository = TradingRepository([_prediction(0.01)])

        entry = TradingAgentService(repository=repository).run_once(symbol="BTCUSDT", interval="1m")

        self.assertEqual(entry.action, "buy")
        self.assertEqual(entry.requested_usdt_amount, 25.0)
        self.assertEqual(entry.risk_status, "approved")
        self.assertEqual(entry.prediction_journal_ids, (7,))

    def test_buy_is_rejected_when_balance_is_insufficient(self) -> None:
        repository = TradingRepository([_prediction(0.01)])

        entry = TradingAgentService(repository=repository).run_once(
            symbol="BTCUSDT",
            interval="1m",
            portfolio=PortfolioSnapshot(available_usdt=10.0),
        )

        self.assertEqual(entry.action, "buy")
        self.assertEqual(entry.risk_status, "rejected")
        self.assertEqual(entry.risk_violations[0]["rule"], "insufficient_usdt")

    def test_spot_demo_mode_is_rejected_until_adapter_exists(self) -> None:
        with self.assertRaisesRegex(ValueError, "not implemented"):
            TradingAgentService(repository=TradingRepository()).run_once(
                symbol="BTCUSDT",
                interval="1m",
                mode="spot-demo",
            )

    def test_low_prediction_return_produces_hold(self) -> None:
        repository = TradingRepository([_prediction(0.0001)])

        entry = TradingAgentService(repository=repository).run_once(
            symbol="BTCUSDT",
            interval="1m",
            risk_config=RiskConfig(min_predicted_return=0.0005),
        )

        self.assertEqual(entry.action, "hold")
        self.assertEqual(entry.risk_status, "skipped")


if __name__ == "__main__":
    unittest.main()
