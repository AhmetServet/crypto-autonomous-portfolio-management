"""Unit tests for prediction journal entities and service behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from dataclasses import replace
from decimal import Decimal
import pickle
import tempfile
import unittest
from pathlib import Path

from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionJournalEntry, prediction_direction
from capm.services.prediction_journal import PredictionJournalService, artifact_sha256
from capm.services.prediction_runtime import RuntimePrediction


def _candle(open_time: datetime, close: str) -> OHLCV:
    return OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1"),
        quote_asset_volume=Decimal("1"),
        trade_count=1,
        taker_buy_base_asset_volume=Decimal("1"),
        taker_buy_quote_asset_volume=Decimal("1"),
    )


class JournalRepository:
    """In-memory prediction journal repository double."""

    def __init__(self) -> None:
        self.entry: PredictionJournalEntry | None = None
        self.settlements = []

    def save_prediction_journal_entry(self, entry: PredictionJournalEntry) -> PredictionJournalEntry:
        self.entry = replace(entry, id=1)
        return self.entry

    def get_unsettled_prediction_journal_entries(self, symbol, interval, until, limit=1000):
        return (self.entry,) if self.entry and self.entry.settled_at is None else ()

    def settle_prediction_journal_entry(self, settlement):
        self.settlements.append(settlement)
        return self.entry

    def summarize_prediction_journal(self, symbol, interval, start_time, end_time, model_name=None):
        raise NotImplementedError


class CandleRepository:
    """In-memory candle repository double."""

    def __init__(self, candle: OHLCV | None) -> None:
        self.candle = candle

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        if self.candle and self.candle.open_time == open_time:
            return self.candle
        return None


class PredictionJournalTests(unittest.TestCase):
    """Exercise journal conversion and settlement."""

    def test_prediction_direction_maps_returns(self) -> None:
        self.assertEqual(prediction_direction(0.1), "up")
        self.assertEqual(prediction_direction(-0.1), "down")
        self.assertEqual(prediction_direction(0.0), "flat")

    def test_artifact_hash_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "model.pkl"
            artifact.write_bytes(b"abc")

            self.assertEqual(artifact_sha256(artifact), artifact_sha256(artifact))

    def test_service_journals_runtime_prediction_and_settles_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "model.pkl"
            with artifact.open("wb") as artifact_file:
                pickle.dump({"model": "fake"}, artifact_file)
            reference_time = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
            prediction_time = datetime(2024, 1, 1, 0, 15, tzinfo=UTC)
            journal_repository = JournalRepository()
            service = PredictionJournalService(
                journal_repository=journal_repository,
                market_data_repository=CandleRepository(_candle(prediction_time, "103")),
            )

            entry = service.journal_prediction(
                RuntimePrediction(
                    artifact_path=str(artifact),
                    artifact_kind="production_tabular",
                    model_name="xgboost",
                    symbol="BTCUSDT",
                    interval="1m",
                    reference_time=reference_time,
                    prediction_time=prediction_time,
                    reference_value=100.0,
                    predicted_value=102.0,
                    predicted_return=0.02,
                    forecast_horizon=15,
                    target_mode="return",
                    feature_names=("sma_20_close",),
                    metadata={"target_field": "close"},
                )
            )
            result = service.settle_predictions(
                symbol="BTCUSDT",
                interval="1m",
                until=prediction_time,
            )

        self.assertEqual(entry.id, 1)
        self.assertEqual(entry.predicted_direction, "up")
        self.assertEqual(result["settled"], 1)
        self.assertEqual(len(journal_repository.settlements), 1)
        settlement = journal_repository.settlements[0]
        self.assertEqual(settlement.actual_value, 103.0)
        self.assertAlmostEqual(settlement.actual_return, 0.03)
        self.assertTrue(settlement.direction_correct)


if __name__ == "__main__":
    unittest.main()
