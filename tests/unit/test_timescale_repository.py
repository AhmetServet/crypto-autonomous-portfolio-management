"""Unit tests for the Timescale market-data repository."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect, select

from capm.domains.features import ComputedIndicatorSet, GAP_REASON_MISSING_DERIVED_ROWS
from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionJournalEntry, PredictionJournalSettlement
from capm.domains.trading import AgentDecisionJournalEntry
from capm.infra.database.models import get_coinpair_model, get_coverage_model, get_feature_model, get_ohlcv_model
from capm.infra.database.timescale import TimescaleMarketDataRepository


def make_candle(
    minute: int,
    *,
    symbol: str = "BTCUSDT",
    close: str = "1.5",
) -> OHLCV:
    """Create a predictable candle for repository tests."""
    return OHLCV(
        symbol=symbol,
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=Decimal("1"),
        high=Decimal("2"),
        low=Decimal("0.5"),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("150"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("60"),
        taker_buy_quote_asset_volume=Decimal("90"),
    )


def make_indicator_set(
    minute: int,
    *,
    symbol: str = "BTCUSDT",
    value: str | None = "1.5",
    is_ready: bool = True,
) -> ComputedIndicatorSet:
    """Create a predictable computed indicator row for repository tests."""
    values = {"sma_3_close": Decimal(value)} if value is not None else {"sma_3_close": None}
    missing_outputs = () if value is not None and is_ready else ("sma_3_close",)
    return ComputedIndicatorSet(
        symbol=symbol,
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        values=values,
        is_ready=is_ready,
        missing_outputs=missing_outputs,
    )


class TimescaleMarketDataRepositoryTests(unittest.TestCase):
    """Exercise CRUD behavior for symbol-scoped OHLCV tables."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.repository = TimescaleMarketDataRepository(
            f"sqlite+pysqlite:///{database_path}"
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _coinpair_rows(self) -> list[object]:
        model = get_coinpair_model(self.repository._schema_name)
        with self.repository._session_factory() as session:
            return session.scalars(select(model).order_by(model.id.asc())).all()

    def _coverage_rows(self, table_name: str, *, symbol: str, interval: str) -> list[object]:
        model = get_coverage_model(table_name, self.repository._schema_name)
        with self.repository._session_factory() as session:
            stmt = (
                select(model)
                .where(model.symbol == symbol, model.interval == interval)
                .order_by(model.start_open_time.asc())
            )
            return [row.to_domain() for row in session.scalars(stmt).all()]

    def test_model_factory_round_trips_domain_entity(self) -> None:
        model = get_ohlcv_model("btc/usdt")
        candle = make_candle(0)

        mapped = model.from_domain(candle)

        self.assertEqual(mapped.to_domain(), candle)

    def test_feature_model_factory_round_trips_domain_entity(self) -> None:
        model = get_feature_model("btc/usdt")
        indicator_set = make_indicator_set(0, value="2.5")

        mapped = model.from_domain(indicator_set)

        self.assertEqual(mapped.to_domain(), indicator_set)

    def test_repository_creates_id_based_tables_and_reads_back_ranges(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(0, symbol="ETHUSDT")])

        btc_candles = self.repository.get_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )
        eth_candle = self.repository.get_candle(
            "ETHUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
        )

        inspector = inspect(self.repository._engine)
        coinpairs = self._coinpair_rows()
        self.assertEqual([(coinpair.id, coinpair.symbol) for coinpair in coinpairs], [(1, "BTCUSDT"), (2, "ETHUSDT")])
        self.assertTrue(inspector.has_table("coinpairs"))
        self.assertTrue(inspector.has_table("ohlcv_coverage"))
        self.assertTrue(inspector.has_table("feature_coverage"))
        self.assertTrue(inspector.has_table("indicator_coverage"))
        self.assertTrue(inspector.has_table("coinpair_1_ohlcv"))
        self.assertTrue(inspector.has_table("coinpair_2_ohlcv"))
        self.assertEqual([candle.open_time.minute for candle in btc_candles], [0, 1])
        self.assertIsNotNone(eth_candle)
        self.assertEqual(eth_candle.symbol, "ETHUSDT")

    def test_repository_upserts_existing_candle(self) -> None:
        candle = make_candle(0)
        updated = make_candle(0, close="9.9")

        self.repository.save_ohlcv_batch([candle])
        self.repository.save_ohlcv_batch([updated])

        stored = self.repository.get_candle("BTCUSDT", "1m", candle.open_time)

        self.assertIsNotNone(stored)
        self.assertEqual(stored.close, Decimal("9.9"))

    def test_repository_returns_latest_and_deletes_ranges(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(2)])

        latest = self.repository.get_latest_candle_time("BTCUSDT", "1m")
        deleted = self.repository.delete_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
        )
        remaining = self.repository.get_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
        )

        self.assertEqual(latest, datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC))
        self.assertEqual(deleted, 2)
        self.assertEqual([candle.open_time.minute for candle in remaining], [0])

    def test_repository_merges_adjacent_ohlcv_coverage_rows(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1)])
        self.repository.save_ohlcv_batch([make_candle(2)])

        coverage_rows = self._coverage_rows("ohlcv_coverage", symbol="BTCUSDT", interval="1m")

        self.assertEqual(len(coverage_rows), 1)
        self.assertEqual(coverage_rows[0].coinpair_id, 1)
        self.assertEqual(coverage_rows[0].table_name, "coinpair_1_ohlcv")
        self.assertEqual(coverage_rows[0].start_open_time, datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC))
        self.assertEqual(coverage_rows[0].end_open_time, datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC))

    def test_repository_plans_gaps_from_ohlcv_coverage(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(3), make_candle(4)])

        fetch_plan = self.repository.plan_candle_fetch(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC),
        )

        self.assertEqual(
            [(item.start_open_time.minute, item.end_open_time.minute) for item in fetch_plan.covered_ranges],
            [(0, 1), (3, 4)],
        )
        self.assertEqual(
            [(item.start_time.minute, item.end_time.minute) for item in fetch_plan.missing_ranges],
            [(2, 3)],
        )

    def test_repository_repairs_ohlcv_coverage_after_delete(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(2), make_candle(3)])

        deleted = self.repository.delete_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )
        coverage_rows = self._coverage_rows("ohlcv_coverage", symbol="BTCUSDT", interval="1m")

        self.assertEqual(deleted, 1)
        self.assertEqual(
            [(row.start_open_time.minute, row.end_open_time.minute) for row in coverage_rows],
            [(0, 0), (2, 3)],
        )

    def test_repository_ignores_empty_batches(self) -> None:
        self.repository.save_ohlcv_batch([])

        self.assertIsNone(self.repository.get_latest_candle_time("BTCUSDT", "1m"))

    def test_repository_batches_large_ohlcv_writes(self) -> None:
        repository = TimescaleMarketDataRepository(
            str(self.repository._engine.url),
            ohlcv_write_batch_size=2,
        )
        candles = [make_candle(minute, close=str(minute + 1)) for minute in range(5)]

        repository.save_ohlcv_batch(candles)

        stored = repository.get_candles(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC),
        )
        self.assertEqual([item.open_time.minute for item in stored], [0, 1, 2, 3, 4])

    def test_repository_crud_for_indicator_rows(self) -> None:
        record = make_indicator_set(0, value="2.1")
        updated = make_indicator_set(0, value="9.9")
        next_record = make_indicator_set(1, value="3.2")

        self.repository.save_indicator_batch([record, next_record])
        self.repository.save_indicator_batch([updated])

        stored = self.repository.get_indicator_set("BTCUSDT", "1m", record.open_time)
        batch = self.repository.get_indicator_batch(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )
        latest = self.repository.get_latest_indicator_time("BTCUSDT", "1m")
        deleted = self.repository.delete_indicator_batch(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )
        remaining = self.repository.get_indicator_batch(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 2, 0, tzinfo=UTC),
        )

        self.assertIsNotNone(stored)
        self.assertEqual(stored.values["sma_3_close"], Decimal("9.9"))
        self.assertEqual([item.open_time.minute for item in batch], [0, 1])
        self.assertEqual(latest, datetime(2024, 1, 1, 0, 1, 0, tzinfo=UTC))
        self.assertEqual(deleted, 1)
        self.assertEqual([item.open_time.minute for item in remaining], [0])

    def test_repository_tracks_indicator_and_feature_coverage(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(2)])
        self.repository.save_indicator_batch([make_indicator_set(1, value="2.0"), make_indicator_set(2, value="3.0")])

        indicator_coverage = self._coverage_rows("indicator_coverage", symbol="BTCUSDT", interval="1m")
        feature_coverage = self._coverage_rows("feature_coverage", symbol="BTCUSDT", interval="1m")

        self.assertEqual(
            [(row.start_open_time.minute, row.end_open_time.minute) for row in indicator_coverage],
            [(1, 2)],
        )
        self.assertEqual(
            [(row.start_open_time.minute, row.end_open_time.minute) for row in feature_coverage],
            [(1, 2)],
        )

        self.repository.save_indicator_batch([make_indicator_set(0, value="1.0")])
        feature_coverage = self._coverage_rows("feature_coverage", symbol="BTCUSDT", interval="1m")
        self.assertEqual(
            [(row.start_open_time.minute, row.end_open_time.minute) for row in feature_coverage],
            [(0, 2)],
        )

    def test_repository_batches_large_indicator_writes(self) -> None:
        repository = TimescaleMarketDataRepository(
            str(self.repository._engine.url),
            feature_write_batch_size=2,
        )
        records = [make_indicator_set(minute, value=str(minute + 1)) for minute in range(5)]

        repository.save_indicator_batch(records)

        stored = repository.get_indicator_batch(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 5, 0, tzinfo=UTC),
        )
        self.assertEqual([item.open_time.minute for item in stored], [0, 1, 2, 3, 4])

    def test_repository_get_feature_rows_and_latest_complete_window(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1), make_candle(2)])
        self.repository.save_indicator_batch(
            [
                make_indicator_set(0, value="1.0"),
                make_indicator_set(1, value="2.0"),
                make_indicator_set(2, value="3.0"),
            ]
        )

        rows = self.repository.get_feature_rows(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 3, 0, tzinfo=UTC),
        )
        window = self.repository.get_latest_complete_window(
            "BTCUSDT",
            "1m",
            2,
            ("sma_3_close",),
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1].indicator_values["sma_3_close"], Decimal("3.0"))
        self.assertIsNotNone(window)
        self.assertTrue(window.is_complete)
        self.assertEqual([row.open_time.minute for row in window.rows], [1, 2])

    def test_repository_marks_missing_derived_rows_in_latest_window(self) -> None:
        self.repository.save_ohlcv_batch([make_candle(0), make_candle(1)])
        self.repository.save_indicator_batch([make_indicator_set(0, value="1.0")])

        window = self.repository.get_latest_complete_window(
            "BTCUSDT",
            "1m",
            2,
            ("sma_3_close",),
        )

        self.assertIsNotNone(window)
        self.assertFalse(window.is_complete)
        self.assertEqual(window.gap_reason, GAP_REASON_MISSING_DERIVED_ROWS)

    def test_repository_persists_settles_and_summarizes_prediction_journal(self) -> None:
        entry = PredictionJournalEntry(
            id=None,
            created_at=None,
            updated_at=None,
            symbol="BTCUSDT",
            interval="1m",
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
            predicted_value=102.0,
            predicted_return=0.02,
            predicted_direction="up",
            feature_names=("sma_3_close",),
            metadata={"source": "test"},
        )

        saved = self.repository.save_prediction_journal_entry(entry)
        duplicate = self.repository.save_prediction_journal_entry(entry)
        unsettled = self.repository.get_unsettled_prediction_journal_entries(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 16, tzinfo=UTC),
        )
        settled = self.repository.settle_prediction_journal_entry(
            PredictionJournalSettlement(
                journal_id=int(saved.id),
                actual_value=103.0,
                actual_return=0.03,
                actual_direction="up",
                absolute_error=1.0,
                absolute_percentage_error=1.0 / 103.0,
                direction_correct=True,
                settled_at=datetime(2024, 1, 1, 0, 16, tzinfo=UTC),
            )
        )
        summary = self.repository.summarize_prediction_journal(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 20, tzinfo=UTC),
        )

        self.assertEqual(saved.id, duplicate.id)
        self.assertEqual(len(unsettled), 1)
        self.assertEqual(settled.actual_value, 103.0)
        self.assertEqual(summary.prediction_count, 1)
        self.assertEqual(summary.settled_count, 1)
        self.assertAlmostEqual(summary.mape, 1.0 / 103.0)
        self.assertEqual(summary.direction_accuracy, 1.0)

    def test_repository_persists_and_summarizes_agent_decision_journal(self) -> None:
        entry = AgentDecisionJournalEntry(
            cycle_id="2024-01-01T00:00:00+00:00:BTCUSDT:1m:dry_run",
            mode="dry-run",
            symbol="BTCUSDT",
            interval="1m",
            reference_time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            action="buy",
            requested_usdt_amount=25.0,
            confidence=0.01,
            reason="xgboost predicted up above threshold",
            prediction_journal_ids=(7,),
            risk_status="approved",
            execution_status="not_submitted",
        )

        saved = self.repository.save_agent_decision_journal_entry(entry)
        duplicate = self.repository.save_agent_decision_journal_entry(entry)
        summary = self.repository.summarize_agent_decision_journal(
            "BTCUSDT",
            "1m",
            datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
        )

        self.assertEqual(saved.id, duplicate.id)
        self.assertEqual(saved.mode, "dry_run")
        self.assertEqual(summary.decision_count, 1)
        self.assertEqual(summary.action_counts["buy"], 1)
        self.assertEqual(summary.risk_status_counts["approved"], 1)
        self.assertEqual(summary.execution_status_counts["not_submitted"], 1)

        updated = self.repository.update_agent_decision_execution(
            int(saved.id),
            execution_status="filled",
            exchange_response={"orderId": 123, "status": "FILLED"},
            exchange_order_id="123",
            exchange_client_order_id="abc",
        )
        self.assertEqual(updated.execution_status, "filled")
        self.assertEqual(updated.exchange_order_id, "123")


if __name__ == "__main__":
    unittest.main()
