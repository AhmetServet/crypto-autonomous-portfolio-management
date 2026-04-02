"""Service layer for computing and assembling indicator-based features."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from capm.core.contracts import FeatureRepositoryPort, FeatureWindowReadPort, MarketDataRepositoryPort
from capm.domains.features import (
    FeatureWindow,
    GAP_REASON_INSUFFICIENT_HISTORY,
    GAP_REASON_MISSING_CANDLE_CONTINUITY,
    IndicatorRegistry,
    IndicatorSpec,
    build_feature_rows,
    build_feature_window,
)
from capm.domains.features.entities import ComputedIndicatorSet, FeatureRow
from capm.domains.features.errors import FeatureGapError, FeatureValidationError
from capm.domains.market_data import interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import ensure_utc


@dataclass(frozen=True, slots=True)
class FeatureBatch:
    """Combined raw-plus-derived feature results for one fetch range."""

    indicator_sets: tuple[ComputedIndicatorSet, ...]
    rows: tuple[FeatureRow, ...]


@dataclass(frozen=True, slots=True)
class FeatureBackfillChunk:
    """Progress information for one persisted feature chunk."""

    chunk_index: int
    chunk_start_time: datetime
    chunk_end_time: datetime
    candles_read: int
    indicator_rows_persisted: int
    last_persisted_open_time: datetime | None


@dataclass(frozen=True, slots=True)
class FeatureBackfillResult:
    """Summary information for a chunked feature backfill."""

    requested_start_time: datetime
    effective_start_time: datetime
    end_time: datetime
    resumed_from: datetime | None
    chunks_processed: int
    candles_read: int
    indicator_rows_persisted: int
    last_persisted_open_time: datetime | None


@dataclass(slots=True)
class IndicatorPipelineService:
    """Compute feature rows and canonical windows from stored candles."""

    market_data_repository: MarketDataRepositoryPort
    feature_repository: FeatureRepositoryPort | None = None
    feature_window_reader: FeatureWindowReadPort | None = None

    def compute_feature_batch(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        indicator_specs: tuple[IndicatorSpec, ...],
    ) -> FeatureBatch:
        """Compute and optionally persist derived features for a time range."""
        normalized_symbol = normalize_symbol(symbol)
        normalized_end_time = ensure_utc(end_time)
        normalized_start_time = ensure_utc(start_time)
        registry = IndicatorRegistry(indicator_specs)
        candles = self.market_data_repository.get_candles(
            normalized_symbol,
            interval,
            normalized_start_time,
            normalized_end_time,
        )
        indicator_sets = registry.compute(candles)
        if self.feature_repository and indicator_sets:
            self.feature_repository.save_indicator_batch(indicator_sets)

        rows = build_feature_rows(candles, indicator_sets)
        return FeatureBatch(
            indicator_sets=tuple(indicator_sets),
            rows=tuple(rows),
        )

    def get_latest_window(
        self,
        *,
        symbol: str,
        interval: str,
        end_time: datetime,
        window_size: int,
        indicator_specs: tuple[IndicatorSpec, ...],
        required_features: tuple[str, ...] = (),
    ) -> FeatureWindow:
        """Return the latest complete-or-incomplete feature window for one symbol."""
        normalized_symbol = normalize_symbol(symbol)
        normalized_end_time = ensure_utc(end_time)
        registry = IndicatorRegistry(indicator_specs)
        required = required_features or tuple(
            output_name
            for spec in registry.enabled_specs
            for output_name in spec.output_names
        )

        interval_delta = interval_to_timedelta(interval)
        history_length = max(window_size + registry.max_lookback - 1, window_size)
        start_time = normalized_end_time - (interval_delta * history_length)

        try:
            batch = self.compute_feature_batch(
                symbol=normalized_symbol,
                interval=interval,
                start_time=start_time,
                end_time=normalized_end_time,
                indicator_specs=indicator_specs,
            )
        except FeatureGapError:
            return FeatureWindow(
                symbol=normalized_symbol,
                interval=interval,
                rows=(),
                requested_features=required,
                is_complete=False,
                gap_reason=GAP_REASON_MISSING_CANDLE_CONTINUITY,
            )
        except FeatureValidationError:
            return FeatureWindow(
                symbol=normalized_symbol,
                interval=interval,
                rows=(),
                requested_features=required,
                is_complete=False,
                gap_reason=GAP_REASON_INSUFFICIENT_HISTORY,
            )

        if self.feature_window_reader is not None:
            stored_window = self.feature_window_reader.get_latest_complete_window(
                normalized_symbol,
                interval,
                window_size,
                required,
            )
            if stored_window is not None:
                return stored_window

        return build_feature_window(
            list(batch.rows),
            symbol=normalized_symbol,
            interval=interval,
            window_size=window_size,
            required_features=required,
        )

    def backfill_feature_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        indicator_specs: tuple[IndicatorSpec, ...],
        chunk_candle_count: int = 2000,
        resume_from_latest: bool = True,
        progress_callback: Callable[[FeatureBackfillChunk], None] | None = None,
    ) -> FeatureBackfillResult:
        """Compute and persist indicators incrementally for a large time range."""
        if self.feature_repository is None:
            raise ValueError("A feature repository is required for backfill persistence.")
        if chunk_candle_count < 1:
            raise ValueError("`chunk_candle_count` must be positive.")

        normalized_symbol = normalize_symbol(symbol)
        normalized_start_time = ensure_utc(start_time)
        normalized_end_time = ensure_utc(end_time)
        registry = IndicatorRegistry(indicator_specs)
        interval_delta = interval_to_timedelta(interval)
        lookback_overlap = max(registry.max_lookback - 1, 0)

        resumed_from: datetime | None = None
        effective_start_time = normalized_start_time
        latest_persisted_time = self.feature_repository.get_latest_indicator_time(
            normalized_symbol,
            interval,
        )
        if resume_from_latest and latest_persisted_time is not None:
            resumed_from = latest_persisted_time
            if latest_persisted_time >= normalized_start_time:
                effective_start_time = max(
                    normalized_start_time,
                    latest_persisted_time - (interval_delta * lookback_overlap),
                )

        if effective_start_time >= normalized_end_time:
            return FeatureBackfillResult(
                requested_start_time=normalized_start_time,
                effective_start_time=effective_start_time,
                end_time=normalized_end_time,
                resumed_from=resumed_from,
                chunks_processed=0,
                candles_read=0,
                indicator_rows_persisted=0,
                last_persisted_open_time=latest_persisted_time,
            )

        cursor = effective_start_time
        chunks_processed = 0
        candles_read = 0
        indicator_rows_persisted = 0
        last_persisted_open_time = latest_persisted_time

        while cursor < normalized_end_time:
            chunk_end_time = min(
                cursor + (interval_delta * chunk_candle_count),
                normalized_end_time,
            )
            compute_start_time = max(
                normalized_start_time,
                cursor - (interval_delta * lookback_overlap),
            )
            candles = self.market_data_repository.get_candles(
                normalized_symbol,
                interval,
                compute_start_time,
                chunk_end_time,
            )
            candles_read += len(candles)

            persisted_indicator_sets: list[ComputedIndicatorSet] = []
            if candles:
                indicator_sets = registry.compute(candles)
                persisted_indicator_sets = [
                    indicator_set
                    for indicator_set in indicator_sets
                    if indicator_set.open_time >= cursor
                ]
                if persisted_indicator_sets:
                    self.feature_repository.save_indicator_batch(persisted_indicator_sets)
                    last_persisted_open_time = persisted_indicator_sets[-1].open_time
                    indicator_rows_persisted += len(persisted_indicator_sets)

            chunks_processed += 1
            if progress_callback is not None:
                progress_callback(
                    FeatureBackfillChunk(
                        chunk_index=chunks_processed,
                        chunk_start_time=cursor,
                        chunk_end_time=chunk_end_time,
                        candles_read=len(candles),
                        indicator_rows_persisted=len(persisted_indicator_sets),
                        last_persisted_open_time=last_persisted_open_time,
                    )
                )
            cursor = chunk_end_time

        return FeatureBackfillResult(
            requested_start_time=normalized_start_time,
            effective_start_time=effective_start_time,
            end_time=normalized_end_time,
            resumed_from=resumed_from,
            chunks_processed=chunks_processed,
            candles_read=candles_read,
            indicator_rows_persisted=indicator_rows_persisted,
            last_persisted_open_time=last_persisted_open_time,
        )
