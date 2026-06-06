"""Contracts for prediction datasets, models, and artifact persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from capm.domains.prediction import (
    ForecastDataset,
    ForecastRequest,
    PredictionJournalEntry,
    PredictionJournalSettlement,
    PredictionJournalSummary,
    SequencePredictionInput,
    SequenceTrainingInput,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
    TabularPredictionInput,
    TabularTrainingInput,
)

TrainingInput = StatisticalTrainingInput | TabularTrainingInput | SequenceTrainingInput
PredictionInput = StatisticalPredictionInput | TabularPredictionInput | SequencePredictionInput


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


class PredictionJournalRepositoryPort(Protocol):
    """Persists and settles runtime prediction journal rows."""

    def save_prediction_journal_entry(self, entry: PredictionJournalEntry) -> PredictionJournalEntry:
        """Insert or return one idempotent prediction journal row."""

    def get_unsettled_prediction_journal_entries(
        self,
        symbol: str,
        interval: str,
        until: datetime,
        limit: int = 1000,
    ) -> tuple[PredictionJournalEntry, ...]:
        """Return unsettled entries whose target prediction time has passed."""

    def list_recent_prediction_journal_entries(
        self,
        symbol: str,
        interval: str,
        limit: int = 20,
    ) -> tuple[PredictionJournalEntry, ...]:
        """Return recent prediction journal rows for observability."""

    def settle_prediction_journal_entry(self, settlement: PredictionJournalSettlement) -> PredictionJournalEntry:
        """Persist actual outcome fields for one journal entry."""

    def summarize_prediction_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        model_name: str | None = None,
    ) -> PredictionJournalSummary:
        """Return aggregate journal metrics for a time range."""
