"""Contracts for derived feature persistence and retrieval."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from capm.domains.features import ComputedIndicatorSet, FeatureRow, FeatureWindow


class FeatureRepositoryPort(Protocol):
    """Abstracts persistence of candle-aligned derived indicator values."""

    def save_indicator_batch(self, records: list[ComputedIndicatorSet]) -> None:
        """Create or update derived indicator values for one or more candles."""

    def get_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[ComputedIndicatorSet]:
        """Read derived indicator values for a half-open time range."""

    def get_indicator_set(
        self,
        symbol: str,
        interval: str,
        open_time: datetime,
    ) -> ComputedIndicatorSet | None:
        """Read one derived indicator row by symbol, interval, and timestamp."""

    def get_latest_indicator_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the latest persisted indicator timestamp for one symbol and interval."""

    def delete_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Delete derived indicator values for a half-open time range."""


class FeatureWindowReadPort(Protocol):
    """Abstracts reads of canonical feature rows and windows."""

    def get_feature_rows(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[FeatureRow]:
        """Read canonical feature rows for a half-open time range."""

    def get_latest_complete_window(
        self,
        symbol: str,
        interval: str,
        window_size: int,
        required_features: tuple[str, ...],
    ) -> FeatureWindow | None:
        """Read the latest complete feature window if one is already materialized."""
