"""Database-backed dataset loading for prediction experiments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from capm.core.contracts import FeatureWindowReadPort, MarketDataRepositoryPort
from capm.domains.prediction import ForecastDataset, ForecastRequest, PredictionValidationError


@dataclass(slots=True)
class PredictionDatasetLoader:
    """Loads canonical forecast datasets from repository ports."""

    market_data_repository: MarketDataRepositoryPort
    feature_window_reader: FeatureWindowReadPort | None = None
    progress_callback: Callable[[str], None] | None = None

    def _emit_progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)

    def load_statistical_dataset(self, request: ForecastRequest) -> ForecastDataset:
        """Load a candle-backed dataset for statistical models."""
        if request.start_time is None or request.end_time is None:
            raise PredictionValidationError("Statistical datasets require both `start_time` and `end_time`.")

        self._emit_progress(
            f"Loading candle dataset for {request.symbol} {request.interval} from "
            f"{request.start_time.isoformat()} to {request.end_time.isoformat()}."
        )
        candles = self.market_data_repository.get_candles(
            request.symbol,
            request.interval,
            request.start_time,
            request.end_time,
        )
        if not candles:
            raise PredictionValidationError(
                "No stored candles were found for "
                f"{request.symbol} {request.interval} between "
                f"{request.start_time.isoformat()} and {request.end_time.isoformat()}. "
                "Ingest OHLCV for that range before running this experiment."
            )
        self._emit_progress(f"Loaded {len(candles)} candle rows.")
        return ForecastDataset(
            symbol=request.symbol,
            interval=request.interval,
            rows=tuple(candles),
            target_field=request.target_field,
            feature_names=(),
            window_size=request.window_size,
            forecast_horizon=request.forecast_horizon,
        )

    def load_tabular_dataset(
        self,
        request: ForecastRequest,
        *,
        required_features: tuple[str, ...] = (),
    ) -> ForecastDataset:
        """Load a feature-row-backed dataset for tabular ML models."""
        if self.feature_window_reader is None:
            raise PredictionValidationError("A feature-window reader is required for tabular datasets.")
        if request.start_time is None or request.end_time is None:
            raise PredictionValidationError("Tabular datasets require both `start_time` and `end_time`.")

        feature_summary = ", ".join(required_features) if required_features else "all available features"
        self._emit_progress(
            f"Loading feature dataset for {request.symbol} {request.interval} from "
            f"{request.start_time.isoformat()} to {request.end_time.isoformat()} "
            f"with required features: {feature_summary}."
        )
        rows = self.feature_window_reader.get_feature_rows(
            request.symbol,
            request.interval,
            request.start_time,
            request.end_time,
        )
        if not rows:
            raise PredictionValidationError(
                "No stored feature rows were found for "
                f"{request.symbol} {request.interval} between "
                f"{request.start_time.isoformat()} and {request.end_time.isoformat()}. "
                "Backfill and persist indicators for that range before running ML experiments."
            )
        self._emit_progress(f"Loaded {len(rows)} feature rows.")
        return ForecastDataset(
            symbol=request.symbol,
            interval=request.interval,
            rows=tuple(rows),
            target_field=request.target_field,
            feature_names=required_features,
            window_size=request.window_size,
            forecast_horizon=request.forecast_horizon,
        )
