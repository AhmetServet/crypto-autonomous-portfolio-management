"""Unit tests for experiment CLI helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.domains.prediction import ForecastResult
from capm.experiments.walk_forward import merge_forecast_results


class MergeForecastResultsTests(unittest.TestCase):
    """Exercise forecast result merging for backtests."""

    def test_merge_concatenates_splits_and_reference_values(self) -> None:
        a = ForecastResult(
            symbol="BTCUSDT",
            interval="1m",
            model_name="arima",
            prediction_times=(datetime(2024, 1, 1, 0, 1, tzinfo=UTC),),
            predicted_values=(101.0,),
            actual_values=(102.0,),
            forecast_horizon=1,
            metadata={"split_id": "split-000", "reference_values": [100.0]},
        )
        b = ForecastResult(
            symbol="BTCUSDT",
            interval="1m",
            model_name="arima",
            prediction_times=(datetime(2024, 1, 1, 0, 2, tzinfo=UTC),),
            predicted_values=(103.0,),
            actual_values=(104.0,),
            forecast_horizon=1,
            metadata={"split_id": "split-001", "reference_values": [102.0]},
        )

        merged = merge_forecast_results((a, b))

        self.assertEqual(merged.prediction_times, a.prediction_times + b.prediction_times)
        self.assertEqual(merged.predicted_values, (101.0, 103.0))
        self.assertEqual(merged.metadata["reference_values"], [100.0, 102.0])


if __name__ == "__main__":
    unittest.main()
