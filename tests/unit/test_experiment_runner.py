"""Unit tests for the walk-forward experiment runner."""

from __future__ import annotations

import pickle
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from capm.domains.market_data import OHLCV
from capm.domains.prediction import ForecastDataset, ForecastRequest
from capm.services.training import LocalArtifactStore, WalkForwardExperimentRunner


def make_candle(minute: int) -> OHLCV:
    """Create a predictable candle for runner tests."""
    close_value = Decimal(str(minute + 1))
    return OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=close_value,
        high=close_value,
        low=close_value,
        close=close_value,
        volume=Decimal("100"),
        quote_asset_volume=Decimal("100"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("50"),
        taker_buy_quote_asset_volume=Decimal("50"),
    )


class FakeDatasetLoader:
    """Test double that returns a preconstructed forecast dataset."""

    def __init__(self, dataset: ForecastDataset) -> None:
        self.dataset = dataset

    def load_statistical_dataset(self, request: ForecastRequest) -> ForecastDataset:
        return self.dataset

    def load_tabular_dataset(
        self,
        request: ForecastRequest,
        *,
        required_features: tuple[str, ...] = (),
    ) -> ForecastDataset:
        raise AssertionError("This test exercises the statistical path only.")


class PerfectStepModel:
    """Fake model that predicts `reference + 1` for the next candle."""

    name = "arima"
    family = "statistical"

    def fit(self, training_input) -> dict[str, object]:
        return {"training_rows": len(training_input.target_values)}

    def predict(self, prediction_input) -> tuple[float, dict[str, object]]:
        return prediction_input.reference_value + 1.0, {"prediction_time": prediction_input.prediction_time.isoformat()}


class ExperimentRunnerTests(unittest.TestCase):
    """Exercise walk-forward orchestration with a fake model."""

    def test_runner_emits_split_and_aggregate_reports(self) -> None:
        dataset = ForecastDataset(
            symbol="BTCUSDT",
            interval="1m",
            rows=tuple(make_candle(index) for index in range(8)),
            target_field="close",
            feature_names=(),
            window_size=3,
            forecast_horizon=1,
        )
        request = ForecastRequest(
            symbol="BTCUSDT",
            interval="1m",
            window_size=3,
            forecast_horizon=1,
            start_time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 0, 8, tzinfo=UTC),
            model_name="arima",
        )

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        progress_messages: list[str] = []
        runner = WalkForwardExperimentRunner(
            dataset_loader=FakeDatasetLoader(dataset),
            artifact_store=LocalArtifactStore(Path(temp_dir.name)),
            progress_callback=progress_messages.append,
        )

        with patch("capm.services.training.experiment_runner.get_model_family", return_value="statistical"), patch(
            "capm.services.training.experiment_runner.create_model",
            return_value=PerfectStepModel(),
        ):
            summary = runner.run(request, validation_size=2)

        self.assertEqual(len(summary.split_results), 2)
        self.assertEqual(len(summary.evaluation_reports), 2)
        self.assertAlmostEqual(summary.aggregate_report.rmse, 0.0)
        self.assertAlmostEqual(summary.aggregate_report.mape, 0.0)
        self.assertAlmostEqual(summary.aggregate_report.direction_accuracy, 1.0)
        run_path = Path(temp_dir.name) / summary.run_id
        self.assertTrue((run_path / "summary.json").exists())
        self.assertTrue((run_path / "split_predictions.json").exists())
        self.assertTrue((run_path / "split_reports.json").exists())
        self.assertTrue((run_path / "trained_models.pkl").exists())
        self.assertFalse((run_path / "split-000").exists())
        with (run_path / "trained_models.pkl").open("rb") as model_artifact:
            trained_models = pickle.load(model_artifact)
        self.assertEqual(trained_models["saved_model_scope"], "latest_model_per_split")
        self.assertEqual(len(trained_models["models"]), 2)
        self.assertTrue(any("Running split 1/2" in message for message in progress_messages))
        self.assertTrue(any("Completed run" in message for message in progress_messages))


if __name__ == "__main__":
    unittest.main()
