"""Unit tests for model registry and wrapper construction."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.domains.prediction import StatisticalTrainingInput

from capm.models import create_model


class ModelRegistryTests(unittest.TestCase):
    """Exercise basic wrapper construction."""

    def test_create_model_constructs_wrappers_with_slots_backing_fields(self) -> None:
        arima = create_model("arima")
        prophet = create_model("prophet")
        xgboost = create_model("xgboost")
        lightgbm = create_model("lightgbm")

        self.assertEqual(arima.name, "arima")
        self.assertEqual(prophet.name, "prophet")
        self.assertEqual(xgboost.name, "xgboost")
        self.assertEqual(lightgbm.name, "lightgbm")

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


if __name__ == "__main__":
    unittest.main()
