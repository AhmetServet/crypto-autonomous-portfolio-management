"""Service layer for prediction journal writes, settlement, and summaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from capm.core.contracts import MarketDataRepositoryPort, PredictionJournalRepositoryPort
from capm.domains.market_data.entities import ensure_utc
from capm.domains.prediction import (
    PredictionJournalEntry,
    PredictionJournalSettlement,
    PredictionJournalSummary,
    prediction_direction,
)
from capm.services.prediction_runtime import RuntimePrediction


def artifact_sha256(path: str | Path) -> str:
    """Return the SHA256 hash for a model artifact file."""
    artifact_path = Path(path)
    digest = hashlib.sha256()
    with artifact_path.open("rb") as artifact_file:
        for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Round-trip metadata through JSON defaults to keep DB JSON payloads safe."""
    return json.loads(json.dumps(value, default=str))


@dataclass(slots=True)
class PredictionJournalService:
    """Coordinates prediction journal persistence and settlement."""

    journal_repository: PredictionJournalRepositoryPort
    market_data_repository: MarketDataRepositoryPort

    def journal_prediction(self, prediction: RuntimePrediction) -> PredictionJournalEntry:
        """Persist one runtime prediction and return the journal row."""
        entry = PredictionJournalEntry(
            id=None,
            created_at=None,
            updated_at=None,
            symbol=prediction.symbol,
            interval=prediction.interval,
            model_name=prediction.model_name,
            artifact_kind=prediction.artifact_kind,
            artifact_path=prediction.artifact_path,
            artifact_sha256=artifact_sha256(prediction.artifact_path),
            reference_time=prediction.reference_time,
            prediction_time=prediction.prediction_time,
            forecast_horizon=prediction.forecast_horizon,
            target_field=str(prediction.metadata.get("target_field", "close")),
            target_mode=prediction.target_mode,
            reference_value=prediction.reference_value,
            predicted_value=prediction.predicted_value,
            predicted_return=prediction.predicted_return,
            predicted_direction=prediction_direction(prediction.predicted_return),
            feature_names=prediction.feature_names,
            metadata=_json_safe_metadata(prediction.metadata),
        )
        return self.journal_repository.save_prediction_journal_entry(entry)

    def settle_predictions(
        self,
        *,
        symbol: str,
        interval: str,
        until: datetime,
        limit: int = 1000,
    ) -> dict[str, int]:
        """Settle unresolved prediction rows whose target candles exist."""
        entries = self.journal_repository.get_unsettled_prediction_journal_entries(
            symbol=symbol,
            interval=interval,
            until=until,
            limit=limit,
        )
        settled = 0
        skipped_missing_candle = 0
        for entry in entries:
            candle = self.market_data_repository.get_candle(entry.symbol, entry.interval, entry.prediction_time)
            if candle is None:
                skipped_missing_candle += 1
                continue
            actual_value = float(getattr(candle, entry.target_field))
            if entry.reference_value == 0:
                skipped_missing_candle += 1
                continue
            actual_return = (actual_value - entry.reference_value) / entry.reference_value
            absolute_error = abs(entry.predicted_value - actual_value)
            absolute_percentage_error = absolute_error / abs(actual_value) if actual_value else 0.0
            actual_direction = prediction_direction(actual_return)
            settlement = PredictionJournalSettlement(
                journal_id=int(entry.id),
                actual_value=actual_value,
                actual_return=actual_return,
                actual_direction=actual_direction,
                absolute_error=absolute_error,
                absolute_percentage_error=absolute_percentage_error,
                direction_correct=entry.predicted_direction == actual_direction,
                settled_at=datetime.now(UTC),
            )
            self.journal_repository.settle_prediction_journal_entry(settlement)
            settled += 1
        return {
            "candidates": len(entries),
            "settled": settled,
            "skipped_missing_candle": skipped_missing_candle,
        }

    def summarize(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        model_name: str | None = None,
    ) -> PredictionJournalSummary:
        """Return aggregate journal metrics."""
        return self.journal_repository.summarize_prediction_journal(
            symbol=symbol,
            interval=interval,
            start_time=ensure_utc(start_time),
            end_time=ensure_utc(end_time),
            model_name=model_name,
        )
