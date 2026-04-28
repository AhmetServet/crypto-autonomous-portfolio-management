"""Contracts for prediction datasets, models, and artifact persistence."""

from __future__ import annotations

from typing import Any, Protocol

from capm.domains.prediction.entities import (
    ForecastDataset,
    ForecastRequest,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
    TabularPredictionInput,
    TabularTrainingInput,
)

TrainingInput = StatisticalTrainingInput | TabularTrainingInput
PredictionInput = StatisticalPredictionInput | TabularPredictionInput


class DatasetLoaderPort(Protocol):
    """Abstracts database-backed dataset reads for forecasting experiments."""

    def load_statistical_dataset(self, request: ForecastRequest) -> ForecastDataset:
        """Load a candle-backed dataset for statistical forecasting models."""

    def load_tabular_dataset(
        self,
        request: ForecastRequest,
        *,
        required_features: tuple[str, ...] = (),
    ) -> ForecastDataset:
        """Load a feature-row-backed dataset for tabular forecasting models."""


class ForecastModelPort(Protocol):
    """Stable model contract shared by all prediction wrappers."""

    name: str
    family: str

    def fit(self, training_input: TrainingInput) -> dict[str, Any]:
        """Fit the model on one prepared training slice."""

    def predict(self, prediction_input: PredictionInput) -> tuple[float, dict[str, Any]]:
        """Return one forecast value plus optional metadata."""


class ArtifactStorePort(Protocol):
    """Persists experiment artifacts under a deterministic run directory."""

    def write_json(self, *, run_id: str, relative_path: str, payload: Any) -> str:
        """Persist one JSON-serializable payload and return its path."""

    def write_pickle(self, *, run_id: str, relative_path: str, payload: Any) -> str:
        """Persist one pickle payload and return its path."""
