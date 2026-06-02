"""Unit tests for the deterministic trading-agent dry-run slice."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionJournalEntry
from capm.domains.trading import PortfolioSnapshot, RiskConfig
from capm.domains.trading import DecisionAction, ProposedDecision
from capm.services.llm_decision_policy import LLMDecisionBatch
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

    def get_candles(self, symbol, interval, start_time, end_time):
        return [self.candle]

    def get_indicator_set(self, symbol, interval, open_time):
        return None

    def get_latest_prediction_journal_entries(self, symbol, interval, reference_time, stale_after):
        return self.predictions

    def save_agent_decision_journal_entry(self, entry):
        saved = replace(entry, id=1)
        self.saved.append(saved)
        return saved

    def update_agent_decision_execution(self, journal_id, **values):
        self.saved[-1] = replace(self.saved[-1], **values)
        return self.saved[-1]

    def get_available_symbols(self, interval):
        return ("BTCUSDT",)


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
        with self.assertRaisesRegex(ValueError, "dry-run mode only"):
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

    def test_llm_path_uses_dynamic_symbols_and_journals_provider_metadata(self) -> None:
        class Policy:
            def decide_batch(self, requests):
                return LLMDecisionBatch(
                    decisions={
                        "BTCUSDT": ProposedDecision(
                            action=DecisionAction.HOLD,
                            confidence=0.4,
                            reason="wait",
                        )
                    },
                    system_prompt="system prompt",
                    prompt="prompt",
                    raw_response="response",
                    attempts=1,
                    model="model",
                    provider_host="provider.example",
                    latency_seconds=0.1,
                    usage={"total_tokens": 10},
                )

        repository = TradingRepository()

        entries = TradingAgentService(repository=repository).run_llm_once(interval="1m", llm_policy=Policy())

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].symbol, "BTCUSDT")
        self.assertEqual(entries[0].metadata["policy"], "llm")
        self.assertEqual(entries[0].metadata["llm_raw_response"], "response")

    def test_spot_demo_llm_path_submits_approved_order(self) -> None:
        class Policy:
            def decide_batch(self, requests):
                return LLMDecisionBatch(
                    decisions={"BTCUSDT": ProposedDecision(action=DecisionAction.BUY, requested_usdt_amount=10, confidence=0.8)},
                    system_prompt="system",
                    prompt="prompt",
                    raw_response="response",
                    attempts=1,
                    model="model",
                    provider_host="provider.example",
                    latency_seconds=0.1,
                    usage={},
                )

        class Exchange:
            def get_portfolio(self, symbol):
                return PortfolioSnapshot(available_usdt=100)

            def submit_market_order(self, symbol, decision):
                return {"orderId": 123, "clientOrderId": "abc", "status": "FILLED"}

            def get_order(self, symbol, order_id):
                return {"orderId": int(order_id), "clientOrderId": "abc", "status": "FILLED"}

        entries = TradingAgentService(repository=TradingRepository(), exchange_adapter=Exchange()).run_llm_once(
            interval="1m",
            mode="spot-demo",
            llm_policy=Policy(),
        )

        self.assertEqual(entries[0].execution_status, "filled")
        self.assertEqual(entries[0].exchange_order_id, "123")
        self.assertEqual(entries[0].exchange_response["reconciliation"]["status"], "FILLED")


if __name__ == "__main__":
    unittest.main()
