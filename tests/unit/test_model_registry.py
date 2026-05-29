"""Unit tests for model registry and wrapper construction."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.domains.prediction import StatisticalTrainingInput

from capm.models import create_model
from capm.models.deep_learning import resolve_torch_device
from capm.models.deep_learning.base import torch
from capm.models.statistical.prophet_model import pd, _to_prophet_timestamp


class ModelRegistryTests(unittest.TestCase):
    """Exercise basic wrapper construction."""

    def test_create_model_constructs_wrappers_with_slots_backing_fields(self) -> None:
        arima = create_model("arima")
        prophet = create_model("prophet")
        xgboost = create_model("xgboost")
        lightgbm = create_model("lightgbm")
        lstm = create_model("lstm")
        gru = create_model("gru")

        self.assertEqual(arima.name, "arima")
        self.assertEqual(prophet.name, "prophet")
        self.assertEqual(xgboost.name, "xgboost")
        self.assertEqual(lightgbm.name, "lightgbm")
        self.assertEqual(lstm.name, "lstm")
        self.assertEqual(gru.name, "gru")

    @unittest.skipIf(torch is None, "torch is not installed")
    def test_deep_learning_auto_device_prefers_available_accelerator_or_cpu(self) -> None:
        device = resolve_torch_device("auto")

        self.assertIn(device.type, {"cuda", "mps", "cpu"})

    def test_arima_builds_frequency_aware_training_series(self) -> None:
        arima = create_model("arima")
        training_input = StatisticalTrainingInput(
            timestamps=(
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 1, tzinfo=UTC),
                datetime(2024, 1, 1, 0, 2, tzinfo=UTC),
            ),
            target_values=(1.0, 2.0, 3.0),
            interval="1m",
        )

        series = arima._build_training_series(training_input)

        self.assertIsNotNone(series.index.freq)

    @unittest.skipIf(pd is None, "pandas is not installed")
    def test_prophet_timestamp_adapter_strips_utc_timezone(self) -> None:
        timestamp = _to_prophet_timestamp(datetime(2024, 1, 1, 0, 0, tzinfo=UTC))

        self.assertIsNone(timestamp.tzinfo)
        self.assertEqual(str(timestamp), "2024-01-01 00:00:00")


if __name__ == "__main__":
    unittest.main()
