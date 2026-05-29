"""Unit tests for deep-learning sequence dataset shaping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import unittest

from capm.domains.features import FeatureRow
from capm.domains.market_data import OHLCV
from capm.domains.prediction import PredictionValidationError
from capm.services.training.sequence_dataset import FeatureScaler, build_sequence_dataset


def _feature_row(index: int, *, ready: bool = True, missing: bool = False) -> FeatureRow:
    open_time = datetime(2024, 1, 1, 0, index, tzinfo=UTC)
    close = Decimal(str(100 + index))
    return FeatureRow(
        candle=OHLCV(
            symbol="BTCUSDT",
            interval="1m",
            open_time=open_time,
            close_time=open_time + timedelta(minutes=1),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=Decimal("1"),
            quote_asset_volume=Decimal("1"),
            trade_count=1,
            taker_buy_base_asset_volume=Decimal("1"),
            taker_buy_quote_asset_volume=Decimal("1"),
        ),
        indicator_values={
            "sma_20_close": None if missing else Decimal(str(index)),
            "rsi_14_close": Decimal(str(50 + index)),
        },
        is_feature_ready=ready,
    )


class SequenceDatasetTests(unittest.TestCase):
    """Exercise sequence shaping and scaler behavior."""

    def test_build_sequence_dataset_aligns_windows_and_return_targets(self) -> None:
        rows = tuple(_feature_row(index) for index in range(6))
        scaler = FeatureScaler.fit(
            tuple((float(row.indicator_values["sma_20_close"]), float(row.indicator_values["rsi_14_close"])) for row in rows[:4]),
            feature_names=("sma_20_close", "rsi_14_close"),
            mode="none",
        )

        dataset = build_sequence_dataset(
            rows=rows,
            feature_names=("sma_20_close", "rsi_14_close"),
            sequence_length=3,
            forecast_horizon=2,
            target_field="close",
            target_mode="return",
            start_index=0,
            end_index=4,
            scaler=scaler,
        )

        self.assertEqual(len(dataset.sequences), 2)
        self.assertEqual(dataset.timestamps[0], rows[2].open_time)
        self.assertEqual(dataset.sequences[0], ((0.0, 50.0), (1.0, 51.0), (2.0, 52.0)))
        self.assertAlmostEqual(dataset.target_values[0], (104.0 - 102.0) / 102.0)
        self.assertEqual(dataset.actual_values[0], 104.0)

    def test_scaler_fits_zscore_on_training_rows(self) -> None:
        scaler = FeatureScaler.fit(
            ((1.0, 10.0), (3.0, 20.0), (5.0, 30.0)),
            feature_names=("a", "b"),
            mode="zscore",
        )

        transformed = scaler.transform_row((3.0, 20.0))

        self.assertAlmostEqual(transformed[0], 0.0)
        self.assertAlmostEqual(transformed[1], 0.0)

    def test_build_sequence_dataset_rejects_missing_features(self) -> None:
        rows = tuple(_feature_row(index, missing=index == 2) for index in range(5))

        with self.assertRaises(PredictionValidationError):
            build_sequence_dataset(
                rows=rows,
                feature_names=("sma_20_close",),
                sequence_length=3,
                forecast_horizon=1,
                target_field="close",
                target_mode="return",
                start_index=0,
                end_index=4,
            )


if __name__ == "__main__":
    unittest.main()
