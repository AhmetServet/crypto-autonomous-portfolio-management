"""Unit tests for runtime prediction from persisted model artifacts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pickle
import tempfile
import unittest
from pathlib import Path

from capm.domains.features import FeatureRow, FeatureWindow
from capm.domains.market_data import OHLCV
from capm.domains.prediction import StatisticalPredictionInput, TabularPredictionInput
from capm.services.prediction_runtime import PredictionRuntimeService


def _candle(open_time: datetime, close: str = "100") -> OHLCV:
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


class FixedReturnModel:
    """Test double for a production tabular return model."""

    name = "xgboost"

    def predict(self, prediction_input: TabularPredictionInput) -> tuple[float, dict[str, object]]:
        return 0.02, {"feature_count": len(prediction_input.feature_names)}


class FixedPriceModel:
    """Test double for a saved statistical model."""

    name = "arima"

    def predict(self, prediction_input: StatisticalPredictionInput) -> tuple[float, dict[str, object]]:
        return 105.0, {"forecast_horizon": prediction_input.forecast_horizon}


class RuntimeRepository:
    """Small in-memory repository double for prediction runtime tests."""

    def __init__(self) -> None:
        self.reference_time = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        self.feature_row = FeatureRow(
            candle=_candle(self.reference_time),
            indicator_values={"sma_20_close": Decimal("99.5")},
            is_feature_ready=True,
        )

    def get_latest_complete_window(
        self,
        symbol: str,
        interval: str,
        window_size: int,
        required_features: tuple[str, ...],
    ) -> FeatureWindow:
        return FeatureWindow(
            symbol=symbol,
            interval=interval,
            rows=(self.feature_row,),
            requested_features=required_features,
            is_complete=True,
        )

    def get_feature_rows(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[FeatureRow]:
        return [self.feature_row] if start_time == self.reference_time else []

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime:
        return self.reference_time

    def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[OHLCV]:
        return [_candle(start_time)]


class PredictionRuntimeTests(unittest.TestCase):
    """Exercise production and walk-forward artifact inference."""

    def test_predicts_from_production_tabular_return_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "model.pkl"
            with artifact_path.open("wb") as artifact_file:
                pickle.dump(
                    {
                        "model": FixedReturnModel(),
                        "model_name": "xgboost",
                        "feature_names": ("sma_20_close",),
                        "target_field": "close",
                        "target_mode": "return",
                        "forecast_horizon": 15,
                        "trained_through": "2024-01-01T00:00:00+00:00",
                    },
                    artifact_file,
                )

            prediction = PredictionRuntimeService(RuntimeRepository()).predict(
                artifact_path=artifact_path,
                symbol="BTC/USDT",
                interval="1m",
            )

        self.assertEqual(prediction.artifact_kind, "production_tabular")
        self.assertEqual(prediction.symbol, "BTCUSDT")
        self.assertEqual(prediction.predicted_value, 102.0)
        self.assertAlmostEqual(prediction.predicted_return, 0.02)
        self.assertEqual(prediction.prediction_time, datetime(2024, 1, 1, 0, 15, tzinfo=UTC))

    def test_predicts_from_walk_forward_latest_model_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = Path(temp_dir) / "trained_models.pkl"
            with artifact_path.open("wb") as artifact_file:
                pickle.dump(
                    {
                        "saved_model_scope": "latest_model_per_split",
                        "models": [
                            {
                                "split_id": "split-000",
                                "model_name": "arima",
                                "latest_reference_time": "2024-01-01T00:00:00+00:00",
                                "latest_prediction_time": "2024-01-01T00:15:00+00:00",
                                "model": FixedPriceModel(),
                            }
                        ],
                    },
                    artifact_file,
                )

            prediction = PredictionRuntimeService(RuntimeRepository()).predict(
                artifact_path=artifact_path,
                symbol="BTCUSDT",
                interval="1m",
            )

        self.assertEqual(prediction.artifact_kind, "walk_forward_latest_model")
        self.assertEqual(prediction.model_name, "arima")
        self.assertEqual(prediction.forecast_horizon, 15)
        self.assertEqual(prediction.predicted_value, 105.0)
        self.assertAlmostEqual(prediction.predicted_return, 0.05)


if __name__ == "__main__":
    unittest.main()
