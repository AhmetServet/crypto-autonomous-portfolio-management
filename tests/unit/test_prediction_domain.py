"""Unit tests for prediction-domain helpers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from capm.domains.prediction import (
    ForecastResult,
    ThresholdSignalPolicy,
    build_walk_forward_splits,
    direction_accuracy,
    generate_threshold_signals,
    mape,
    rmse,
)


class PredictionDomainTests(unittest.TestCase):
    """Exercise split, metric, and signal helpers."""

    def test_build_walk_forward_splits_uses_reference_windows(self) -> None:
        splits = build_walk_forward_splits(
            total_rows=8,
            window_size=3,
            forecast_horizon=1,
            validation_size=2,
        )

        self.assertEqual([split.reference_indices for split in splits], [(3, 4), (5, 6)])

    def test_metrics_and_signal_policy_use_reference_values(self) -> None:
        prediction_times = (
            datetime(2024, 1, 1, 0, 4, tzinfo=UTC),
            datetime(2024, 1, 1, 0, 5, tzinfo=UTC),
        )
        result = ForecastResult(
            symbol="BTCUSDT",
            interval="1m",
            model_name="arima",
            prediction_times=prediction_times,
            predicted_values=(105.0, 98.0),
            actual_values=(106.0, 97.0),
            forecast_horizon=1,
            metadata={"reference_values": [100.0, 100.0]},
        )

        self.assertAlmostEqual(rmse(result.predicted_values, result.actual_values), 1.0)
        self.assertAlmostEqual(
            mape(result.predicted_values, result.actual_values),
            ((1 / 106) + (1 / 97)) / 2,
            places=6,
        )
        self.assertEqual(
            direction_accuracy(
                predicted_values=result.predicted_values,
                actual_values=result.actual_values,
                reference_values=(100.0, 100.0),
            ),
            1.0,
        )

        signals = generate_threshold_signals(
            result,
            policy=ThresholdSignalPolicy(buy_threshold=0.03),
        )
        self.assertEqual([signal.action for signal in signals], ["buy", "hold"])


if __name__ == "__main__":
    unittest.main()
