"""Unit tests for prediction dataset adapters."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from capm.domains.features import ComputedIndicatorSet, FeatureRow
from capm.domains.market_data import OHLCV
from capm.domains.prediction import ForecastDataset
from capm.services.training import StatisticalDatasetAdapter, TabularDatasetAdapter


def make_candle(minute: int, *, close: str) -> OHLCV:
    """Create a predictable OHLCV row for adapter tests."""
    return OHLCV(
        symbol="BTCUSDT",
        interval="1m",
        open_time=datetime(2024, 1, 1, 0, minute, 0, tzinfo=UTC),
        close_time=datetime(2024, 1, 1, 0, minute, 59, tzinfo=UTC),
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_asset_volume=Decimal("100"),
        trade_count=10,
        taker_buy_base_asset_volume=Decimal("50"),
        taker_buy_quote_asset_volume=Decimal("50"),
    )


def make_feature_row(minute: int, *, close: str, sma: str, rsi: str) -> FeatureRow:
    """Create a predictable feature row with ready indicators."""
    candle = make_candle(minute, close=close)
    indicator_set = ComputedIndicatorSet(
        symbol="BTCUSDT",
        interval="1m",
        open_time=candle.open_time,
        values={
            "sma_3_close": Decimal(sma),
            "rsi_2_close": Decimal(rsi),
        },
        is_ready=True,
        missing_outputs=(),
    )
    return FeatureRow.from_components(candle, indicator_set)


class PredictionAdapterTests(unittest.TestCase):
    """Exercise statistical and tabular adapter behavior."""

    def test_statistical_adapter_prepares_one_walk_forward_step(self) -> None:
        dataset = ForecastDataset(
            symbol="BTCUSDT",
            interval="1m",
            rows=tuple(make_candle(index, close=str(index + 1)) for index in range(8)),
            target_field="close",
            feature_names=(),
            window_size=3,
            forecast_horizon=1,
        )

        prepared = StatisticalDatasetAdapter().prepare_step(dataset, 3)

        self.assertEqual(prepared.reference_value, 4.0)
        self.assertEqual(prepared.actual_value, 5.0)
        self.assertEqual(prepared.training_input.target_values, (1.0, 2.0, 3.0))

    def test_tabular_adapter_shapes_feature_matrix_and_future_targets(self) -> None:
        dataset = ForecastDataset(
            symbol="BTCUSDT",
            interval="1m",
            rows=tuple(
                make_feature_row(
                    index,
                    close=str(index + 10),
                    sma=str(index + 1),
                    rsi=str(index + 50),
                )
                for index in range(8)
            ),
            target_field="close",
            feature_names=("rsi_2_close", "sma_3_close"),
            window_size=3,
            forecast_horizon=1,
        )

        prepared = TabularDatasetAdapter().prepare_step(dataset, 3)

        self.assertEqual(prepared.reference_value, 13.0)
        self.assertEqual(prepared.actual_value, 14.0)
        self.assertEqual(
            prepared.training_input.feature_matrix,
            (
                (50.0, 1.0),
                (51.0, 2.0),
                (52.0, 3.0),
            ),
        )
        self.assertEqual(prepared.training_input.target_values, (11.0, 12.0, 13.0))
        self.assertEqual(prepared.prediction_input.feature_vector, (53.0, 4.0))


if __name__ == "__main__":
    unittest.main()
