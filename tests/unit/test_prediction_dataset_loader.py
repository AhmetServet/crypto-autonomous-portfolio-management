"""Unit tests for prediction dataset loading and error messages."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from capm.domains.prediction import ForecastRequest, PredictionValidationError
from capm.services.training import PredictionDatasetLoader


class EmptyFeatureRepository:
    """Test double that returns no feature rows."""

    def get_feature_rows(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[object]:
        return []


class EmptyMarketRepository:
    """Test double that returns no candles."""

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[object]:
        return []


class PredictionDatasetLoaderTests(unittest.TestCase):
    """Exercise dataset loader progress and validation behavior."""

    def test_load_tabular_dataset_raises_helpful_error_when_rows_are_missing(self) -> None:
        request = ForecastRequest(
            symbol="BTCUSDT",
            interval="1m",
            start_time=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            end_time=datetime(2024, 1, 1, 1, 0, tzinfo=UTC),
            model_name="xgboost",
        )
        progress_messages: list[str] = []
        loader = PredictionDatasetLoader(
            market_data_repository=EmptyMarketRepository(),
            feature_window_reader=EmptyFeatureRepository(),
            progress_callback=progress_messages.append,
        )

        with self.assertRaises(PredictionValidationError) as context:
            loader.load_tabular_dataset(request, required_features=("sma_20_close",))

        self.assertIn("No stored feature rows were found", str(context.exception))
        self.assertTrue(any("Loading feature dataset" in message for message in progress_messages))


if __name__ == "__main__":
    unittest.main()
