"""PostgreSQL/TimescaleDB repository implementations using SQLAlchemy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import islice
from typing import Any

from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from capm.domains.features import (
    ComputedIndicatorSet,
    FeatureRow,
    FeatureWindow,
    GAP_REASON_MISSING_DERIVED_ROWS,
    build_feature_window,
)
from capm.domains.market_data import CoverageRange, OHLCVFetchPlan, TimeRange, interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import OHLCV, ensure_utc
from capm.domains.prediction import (
    PredictionJournalEntry,
    PredictionJournalSettlement,
    PredictionJournalSummary,
    direction_accuracy,
    mape,
    prediction_direction,
    rmse,
)
from capm.domains.trading import AgentDecisionJournalEntry, AgentDecisionJournalSummary, OperationalRiskSnapshot
from capm.infra.database.models import (
    agent_decision_journal_to_record,
    build_feature_table_name,
    build_ohlcv_table_name,
    candle_to_record,
    get_coinpair_model,
    get_agent_decision_journal_model,
    get_coverage_model,
    get_feature_model,
    get_ohlcv_model,
    get_prediction_journal_model,
    indicator_to_record,
    prediction_journal_to_record,
)


@dataclass(frozen=True, slots=True)
class CoinpairBinding:
    """Resolved physical table names for one logical symbol."""

    id: int
    symbol: str
    ohlcv_table_name: str
    feature_table_name: str


class TimescaleMarketDataRepository:
    """SQLAlchemy repository for raw OHLCV candles and derived feature rows."""

    def __init__(
        self,
        connection_string: str,
        schema_name: str | None = None,
        *,
        ohlcv_write_batch_size: int | None = 500,
        feature_write_batch_size: int = 1000,
        hide_sql_parameters: bool = True,
    ) -> None:
        """Initialize the repository by creating the SQLAlchemy engine."""
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg://", 1)

        self._engine = create_engine(
            connection_string,
            pool_pre_ping=True,
            hide_parameters=hide_sql_parameters,
        )
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False)
        self._schema_name = (
            schema_name.strip() if schema_name and self._engine.dialect.name == "postgresql" else None
        )
        self._ohlcv_write_batch_size = ohlcv_write_batch_size
        self._feature_write_batch_size = feature_write_batch_size
        self._initialized_tables: set[str] = set()
        self._coinpair_model = get_coinpair_model(self._schema_name)
        self._ohlcv_coverage_model = get_coverage_model("ohlcv_coverage", self._schema_name)
        self._feature_coverage_model = get_coverage_model("feature_coverage", self._schema_name)
        self._indicator_coverage_model = get_coverage_model("indicator_coverage", self._schema_name)
        self._prediction_journal_model = get_prediction_journal_model(self._schema_name)
        self._agent_decision_journal_model = get_agent_decision_journal_model(self._schema_name)

    def initialize_schema(self, symbols: Iterable[str] | None = None) -> None:
        """Create metadata plus optional coinpair-scoped market and feature tables."""
        if self._engine.dialect.name == "postgresql":
            self._ensure_timescale_extension()
            self._ensure_schema_exists()
        self._ensure_metadata_tables()
        for symbol in symbols or []:
            self._ensure_market_table(symbol)
            self._ensure_feature_table(symbol)

    def _ensure_timescale_extension(self) -> None:
        """Install the TimescaleDB extension when PostgreSQL is used."""
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    def _ensure_schema_exists(self) -> None:
        """Create the configured schema if it does not already exist."""
        if not self._schema_name:
            return
        with self._engine.begin() as conn:
            quoted_schema_name = conn.dialect.identifier_preparer.quote_identifier(self._schema_name)
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema_name}"))

    def _ensure_metadata_tables(self) -> None:
        """Create static registry and coverage tables."""
        for model in (
            self._coinpair_model,
            self._ohlcv_coverage_model,
            self._feature_coverage_model,
            self._indicator_coverage_model,
            self._prediction_journal_model,
            self._agent_decision_journal_model,
        ):
            self._ensure_static_table(model)

    def _ensure_static_table(self, model: Any) -> None:
        """Create a non-hypertable metadata table once."""
        table_name = model.__tablename__
        if table_name in self._initialized_tables:
            return
        model.__table__.create(self._engine, checkfirst=True)
        self._initialized_tables.add(table_name)

    def _ensure_hypertable(self, table_name: str) -> None:
        """Convert a coinpair table into a TimescaleDB hypertable."""
        relation_name = self._qualified_relation_name(table_name)
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    SELECT create_hypertable(
                        CAST(:relation_name AS regclass),
                        'open_time',
                        chunk_time_interval => INTERVAL '7 days',
                        if_not_exists => TRUE
                    );
                    """
                ),
                {"relation_name": relation_name},
            )

    def _qualified_relation_name(self, table_name: str) -> str:
        """Return the schema-qualified relation name for PostgreSQL operations."""
        if self._schema_name:
            return f'"{self._schema_name}"."{table_name}"'
        return f'"{table_name}"'

    def _get_coinpair_binding(self, symbol: str, *, create: bool) -> CoinpairBinding | None:
        """Resolve or create the id-based physical table mapping for one symbol."""
        normalized_symbol = normalize_symbol(symbol)
        self._ensure_metadata_tables()
        with self._session_factory() as session:
            stmt = select(self._coinpair_model).where(self._coinpair_model.symbol == normalized_symbol)
            coinpair = session.scalars(stmt).first()
            if coinpair is None and not create:
                return None
            if coinpair is None:
                coinpair = self._coinpair_model(symbol=normalized_symbol)
                session.add(coinpair)
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    coinpair = session.scalars(stmt).first()
                else:
                    session.refresh(coinpair)
            if coinpair is None:
                return None
            return CoinpairBinding(
                id=coinpair.id,
                symbol=coinpair.symbol,
                ohlcv_table_name=build_ohlcv_table_name(coinpair.id),
                feature_table_name=build_feature_table_name(coinpair.id),
            )

    def _get_existing_symbol_model(
        self,
        symbol: str,
        table_name: str,
        model_factory: Callable[..., Any],
    ) -> Any:
        """Return a dynamic model only if its backing table exists."""
        model = model_factory(symbol, self._schema_name, table_name=table_name)
        if not inspect(self._engine).has_table(model.__tablename__, schema=self._schema_name):
            return None
        self._initialized_tables.add(model.__tablename__)
        return model

    def _ensure_symbol_table(
        self,
        symbol: str,
        table_name: str,
        model_factory: Callable[..., Any],
    ) -> Any:
        """Create a coinpair-scoped table on first use."""
        model = model_factory(symbol, self._schema_name, table_name=table_name)
        if table_name in self._initialized_tables:
            return model
        model.__table__.create(self._engine, checkfirst=True)
        if self._engine.dialect.name == "postgresql":
            self._ensure_hypertable(table_name)
        self._initialized_tables.add(table_name)
        return model

    def _get_existing_market_model(self, symbol: str) -> Any:
        """Return the OHLCV model if its physical table exists."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return None
        return self._get_existing_symbol_model(binding.symbol, binding.ohlcv_table_name, get_ohlcv_model)

    def _ensure_market_table(self, symbol: str) -> Any:
        """Create the OHLCV table for a symbol on first use."""
        binding = self._get_coinpair_binding(symbol, create=True)
        return self._ensure_symbol_table(binding.symbol, binding.ohlcv_table_name, get_ohlcv_model)

    def _get_existing_feature_model(self, symbol: str) -> Any:
        """Return the derived feature model if its physical table exists."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return None
        return self._get_existing_symbol_model(binding.symbol, binding.feature_table_name, get_feature_model)

    def _ensure_feature_table(self, symbol: str) -> Any:
        """Create the derived feature table for a symbol on first use."""
        binding = self._get_coinpair_binding(symbol, create=True)
        return self._ensure_symbol_table(binding.symbol, binding.feature_table_name, get_feature_model)

    @staticmethod
    def _coverage_model_for_kind(kind: str, repository: "TimescaleMarketDataRepository") -> Any:
        """Return the coverage table model for a logical dataset kind."""
        if kind == "ohlcv":
            return repository._ohlcv_coverage_model
        if kind == "feature":
            return repository._feature_coverage_model
        if kind == "indicator":
            return repository._indicator_coverage_model
        raise ValueError(f"Unsupported coverage kind {kind!r}.")

    @staticmethod
    def _physical_table_name_for_kind(kind: str, binding: CoinpairBinding) -> str:
        """Return the physical table name represented by a coverage kind."""
        if kind == "ohlcv":
            return binding.ohlcv_table_name
        if kind in {"feature", "indicator"}:
            return binding.feature_table_name
        raise ValueError(f"Unsupported coverage kind {kind!r}.")

    def _save_records(
        self,
        *,
        records_by_symbol: dict[str, list[Any]],
        model_resolver: Callable[[str], Any],
        payload_builder: Callable[[Any], dict[str, object]],
        batch_size: int | None = None,
    ) -> None:
        """Persist a grouped batch using upsert or merge semantics."""
        for symbol, symbol_records in records_by_symbol.items():
            model = model_resolver(symbol)
            with self._session_factory() as session:
                for batch in self._batched(symbol_records, batch_size):
                    if self._engine.dialect.name == "postgresql":
                        values = [payload_builder(record) for record in batch]
                        stmt = pg_insert(model).values(values)
                        update_dict = {
                            column.name: getattr(stmt.excluded, column.name)
                            for column in model.__table__.columns
                            if column.name not in {"interval", "open_time"}
                        }
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["interval", "open_time"],
                            set_=update_dict,
                        )
                        session.execute(stmt)
                    else:
                        for record in batch:
                            session.merge(model.from_domain(record))
                session.commit()

    @staticmethod
    def _batched(records: list[Any], batch_size: int | None) -> Iterable[list[Any]]:
        """Yield records in bounded batches while preserving order."""
        if not records:
            return []
        if batch_size is None or batch_size < 1:
            return [list(records)]

        iterator = iter(records)
        batches: list[list[Any]] = []
        while True:
            batch = list(islice(iterator, batch_size))
            if not batch:
                break
            batches.append(batch)
        return batches

    @staticmethod
    def _build_contiguous_ranges(open_times: Iterable[datetime], interval_delta: timedelta) -> list[tuple[datetime, datetime]]:
        """Collapse ordered candle timestamps into inclusive contiguous ranges."""
        unique_times = sorted({ensure_utc(open_time) for open_time in open_times})
        if not unique_times:
            return []

        ranges: list[tuple[datetime, datetime]] = []
        range_start = unique_times[0]
        range_end = unique_times[0]
        for open_time in unique_times[1:]:
            if open_time == range_end + interval_delta:
                range_end = open_time
                continue
            ranges.append((range_start, range_end))
            range_start = open_time
            range_end = open_time
        ranges.append((range_start, range_end))
        return ranges

    def _merge_coverage_ranges(
        self,
        kind: str,
        symbol: str,
        interval: str,
        ranges: Iterable[tuple[datetime, datetime]],
    ) -> None:
        """Merge one or more contiguous ranges into the stored coverage table."""
        binding = self._get_coinpair_binding(symbol, create=True)
        model = self._coverage_model_for_kind(kind, self)
        table_name = self._physical_table_name_for_kind(kind, binding)
        interval_delta = interval_to_timedelta(interval)

        for start_open_time, end_open_time in ranges:
            normalized_start = ensure_utc(start_open_time)
            normalized_end = ensure_utc(end_open_time)
            with self._session_factory() as session:
                overlap_stmt = (
                    select(model)
                    .where(
                        model.coinpair_id == binding.id,
                        model.interval == interval,
                        model.end_open_time >= normalized_start - interval_delta,
                        model.start_open_time <= normalized_end + interval_delta,
                    )
                    .order_by(model.start_open_time.asc())
                )
                overlaps = session.scalars(overlap_stmt).all()
                merged_start = normalized_start
                merged_end = normalized_end
                for coverage_row in overlaps:
                    merged_start = min(merged_start, ensure_utc(coverage_row.start_open_time))
                    merged_end = max(merged_end, ensure_utc(coverage_row.end_open_time))
                    session.delete(coverage_row)
                session.add(
                    model(
                        coinpair_id=binding.id,
                        table_name=table_name,
                        symbol=binding.symbol,
                        interval=interval,
                        start_open_time=merged_start,
                        end_open_time=merged_end,
                    )
                )
                session.commit()

    def _replace_coverage_ranges(
        self,
        kind: str,
        binding: CoinpairBinding,
        interval: str,
        ranges: Iterable[tuple[datetime, datetime]],
    ) -> None:
        """Replace all stored coverage rows for one symbol/interval/dataset."""
        model = self._coverage_model_for_kind(kind, self)
        table_name = self._physical_table_name_for_kind(kind, binding)
        with self._session_factory() as session:
            session.execute(
                delete(model).where(
                    model.coinpair_id == binding.id,
                    model.interval == interval,
                )
            )
            for start_open_time, end_open_time in ranges:
                session.add(
                    model(
                        coinpair_id=binding.id,
                        table_name=table_name,
                        symbol=binding.symbol,
                        interval=interval,
                        start_open_time=ensure_utc(start_open_time),
                        end_open_time=ensure_utc(end_open_time),
                    )
                )
            session.commit()

    def _load_coverage_ranges(
        self,
        kind: str,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[CoverageRange]:
        """Read overlapping coverage metadata rows for a requested time window."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return []

        model = self._coverage_model_for_kind(kind, self)
        normalized_start = ensure_utc(start_time)
        normalized_end = ensure_utc(end_time)
        with self._session_factory() as session:
            stmt = (
                select(model)
                .where(
                    model.coinpair_id == binding.id,
                    model.interval == interval,
                    model.end_open_time >= normalized_start,
                    model.start_open_time < normalized_end,
                )
                .order_by(model.start_open_time.asc())
            )
            return [row.to_domain() for row in session.scalars(stmt).all()]

    def _load_all_coverage_ranges(self, kind: str, symbol: str, interval: str) -> list[CoverageRange]:
        """Read all stored coverage metadata rows for one symbol and interval."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return []

        model = self._coverage_model_for_kind(kind, self)
        with self._session_factory() as session:
            stmt = (
                select(model)
                .where(
                    model.coinpair_id == binding.id,
                    model.interval == interval,
                )
                .order_by(model.start_open_time.asc())
            )
            return [row.to_domain() for row in session.scalars(stmt).all()]

    @staticmethod
    def _build_missing_ranges(
        coverage_ranges: list[CoverageRange],
        interval_delta: timedelta,
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[TimeRange, ...]:
        """Compute the fetch gaps left uncovered by stored metadata rows."""
        normalized_start = ensure_utc(start_time)
        normalized_end = ensure_utc(end_time)
        cursor = normalized_start
        missing_ranges: list[TimeRange] = []

        for coverage_range in coverage_ranges:
            coverage_start = max(normalized_start, coverage_range.start_open_time)
            coverage_end = min(normalized_end, coverage_range.end_open_time + interval_delta)
            if coverage_end <= cursor:
                continue
            if coverage_start > cursor:
                missing_ranges.append(TimeRange(cursor, coverage_start))
            cursor = max(cursor, coverage_end)

        if cursor < normalized_end:
            missing_ranges.append(TimeRange(cursor, normalized_end))
        return tuple(missing_ranges)

    def _refresh_feature_coverage(self, symbol: str, interval: str) -> None:
        """Recompute feature coverage as the intersection of raw and derived coverage."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return

        ohlcv_ranges = self._load_all_coverage_ranges("ohlcv", symbol, interval)
        indicator_ranges = self._load_all_coverage_ranges("indicator", symbol, interval)

        intersections: list[tuple[datetime, datetime]] = []
        raw_index = 0
        indicator_index = 0
        while raw_index < len(ohlcv_ranges) and indicator_index < len(indicator_ranges):
            raw_range = ohlcv_ranges[raw_index]
            indicator_range = indicator_ranges[indicator_index]
            overlap_start = max(raw_range.start_open_time, indicator_range.start_open_time)
            overlap_end = min(raw_range.end_open_time, indicator_range.end_open_time)
            if overlap_start <= overlap_end:
                intersections.append((overlap_start, overlap_end))
            if raw_range.end_open_time < indicator_range.end_open_time:
                raw_index += 1
            else:
                indicator_index += 1

        self._replace_coverage_ranges("feature", binding, interval, intersections)

    def _rebuild_coverage_from_table(self, kind: str, symbol: str, interval: str) -> None:
        """Recompute coverage metadata by scanning persisted rows for one symbol and interval."""
        binding = self._get_coinpair_binding(symbol, create=False)
        if binding is None:
            return

        if kind == "ohlcv":
            model = self._get_existing_market_model(symbol)
        elif kind == "indicator":
            model = self._get_existing_feature_model(symbol)
        else:
            raise ValueError(f"Unsupported rebuild kind {kind!r}.")

        ranges: list[tuple[datetime, datetime]] = []
        if model is not None:
            with self._session_factory() as session:
                stmt = (
                    select(model.open_time)
                    .where(model.interval == interval)
                    .order_by(model.open_time.asc())
                )
                open_times = session.scalars(stmt).all()
            ranges = self._build_contiguous_ranges(open_times, interval_to_timedelta(interval))
        self._replace_coverage_ranges(kind, binding, interval, ranges)
        self._refresh_feature_coverage(symbol, interval)

    def plan_candle_fetch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> OHLCVFetchPlan:
        """Return stored-coverage and missing-gap information for one OHLCV request."""
        coverage_ranges = self._load_coverage_ranges("ohlcv", symbol, interval, start_time, end_time)
        missing_ranges = self._build_missing_ranges(
            coverage_ranges,
            interval_to_timedelta(interval),
            start_time,
            end_time,
        )
        return OHLCVFetchPlan(
            covered_ranges=tuple(coverage_ranges),
            missing_ranges=missing_ranges,
        )

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Create or update a batch of OHLCV candles."""
        if not candles:
            return

        candles_by_symbol: dict[str, list[OHLCV]] = defaultdict(list)
        candles_by_symbol_interval: dict[tuple[str, str], list[OHLCV]] = defaultdict(list)
        for candle in candles:
            candles_by_symbol[candle.symbol].append(candle)
            candles_by_symbol_interval[(candle.symbol, candle.interval)].append(candle)

        self._save_records(
            records_by_symbol=candles_by_symbol,
            model_resolver=self._ensure_market_table,
            payload_builder=candle_to_record,
            batch_size=self._ohlcv_write_batch_size,
        )

        for (symbol, interval), interval_candles in candles_by_symbol_interval.items():
            ranges = self._build_contiguous_ranges(
                [candle.open_time for candle in interval_candles],
                interval_to_timedelta(interval),
            )
            self._merge_coverage_ranges("ohlcv", symbol, interval, ranges)
            self._refresh_feature_coverage(symbol, interval)

    def save_indicator_batch(self, records: list[ComputedIndicatorSet]) -> None:
        """Create or update a batch of derived indicator rows."""
        if not records:
            return

        records_by_symbol: dict[str, list[ComputedIndicatorSet]] = defaultdict(list)
        records_by_symbol_interval: dict[tuple[str, str], list[ComputedIndicatorSet]] = defaultdict(list)
        for record in records:
            records_by_symbol[record.symbol].append(record)
            records_by_symbol_interval[(record.symbol, record.interval)].append(record)

        self._save_records(
            records_by_symbol=records_by_symbol,
            model_resolver=self._ensure_feature_table,
            payload_builder=indicator_to_record,
            batch_size=self._feature_write_batch_size,
        )

        for (symbol, interval), interval_records in records_by_symbol_interval.items():
            ranges = self._build_contiguous_ranges(
                [record.open_time for record in interval_records],
                interval_to_timedelta(interval),
            )
            self._merge_coverage_ranges("indicator", symbol, interval, ranges)
            self._refresh_feature_coverage(symbol, interval)

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the open_time of the latest stored candle for a symbol and interval."""
        model = self._get_existing_market_model(symbol)
        if model is None:
            return None
        with self._session_factory() as session:
            stmt = (
                select(model.open_time)
                .where(model.interval == interval)
                .order_by(model.open_time.desc())
                .limit(1)
            )
            latest = session.scalar(stmt)
            return ensure_utc(latest) if latest else None

    def get_available_symbols(self, interval: str) -> tuple[str, ...]:
        """Return registered symbols that currently have stored candles for an interval."""
        self._ensure_metadata_tables()
        with self._session_factory() as session:
            symbols = tuple(session.scalars(select(self._coinpair_model.symbol).order_by(self._coinpair_model.symbol.asc())).all())
        return tuple(symbol for symbol in symbols if self.get_latest_candle_time(symbol, interval) is not None)

    def get_latest_indicator_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the open_time of the latest stored indicator row for a symbol and interval."""
        model = self._get_existing_feature_model(symbol)
        if model is None:
            return None
        with self._session_factory() as session:
            stmt = (
                select(model.open_time)
                .where(model.interval == interval)
                .order_by(model.open_time.desc())
                .limit(1)
            )
            latest = session.scalar(stmt)
            return ensure_utc(latest) if latest else None

    def get_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> list[OHLCV]:
        """Read candles for a given symbol, interval, and exact time window [start_time, end_time)."""
        model = self._get_existing_market_model(symbol)
        if model is None:
            return []
        with self._session_factory() as session:
            stmt = (
                select(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time,
                )
                .order_by(model.open_time.asc())
            )
            return [result.to_domain() for result in session.scalars(stmt).all()]

    def get_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[ComputedIndicatorSet]:
        """Read derived indicator rows for a given symbol, interval, and exact time window."""
        model = self._get_existing_feature_model(symbol)
        if model is None:
            return []
        with self._session_factory() as session:
            stmt = (
                select(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time,
                )
                .order_by(model.open_time.asc())
            )
            return [result.to_domain() for result in session.scalars(stmt).all()]

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        """Read a single precise candle based on its composite primary key."""
        model = self._get_existing_market_model(symbol)
        if model is None:
            return None
        with self._session_factory() as session:
            stmt = select(model).where(model.interval == interval, model.open_time == open_time)
            result = session.scalars(stmt).first()
            return result.to_domain() if result else None

    def get_indicator_set(
        self,
        symbol: str,
        interval: str,
        open_time: datetime,
    ) -> ComputedIndicatorSet | None:
        """Read a single precise indicator row based on its composite primary key."""
        model = self._get_existing_feature_model(symbol)
        if model is None:
            return None
        with self._session_factory() as session:
            stmt = select(model).where(model.interval == interval, model.open_time == open_time)
            result = session.scalars(stmt).first()
            return result.to_domain() if result else None

    def delete_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> int:
        """Delete candles for a given symbol, interval, and time window. Returns number of rows deleted."""
        model = self._get_existing_market_model(symbol)
        if model is None:
            return 0
        with self._session_factory() as session:
            stmt = (
                delete(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time,
                )
            )
            result = session.execute(stmt)
            session.commit()
        self._rebuild_coverage_from_table("ohlcv", symbol, interval)
        return int(result.rowcount or 0)

    def delete_indicator_batch(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Delete derived indicator rows for a given symbol, interval, and time window."""
        model = self._get_existing_feature_model(symbol)
        if model is None:
            return 0
        with self._session_factory() as session:
            stmt = (
                delete(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time,
                )
            )
            result = session.execute(stmt)
            session.commit()
        self._rebuild_coverage_from_table("indicator", symbol, interval)
        return int(result.rowcount or 0)

    def get_feature_rows(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[FeatureRow]:
        """Read canonical feature rows joined from stored candles and indicator rows."""
        candles = self.get_candles(symbol, interval, start_time, end_time)
        if not candles:
            return []

        indicator_map = {
            indicator_set.open_time: indicator_set
            for indicator_set in self.get_indicator_batch(symbol, interval, start_time, end_time)
        }
        rows: list[FeatureRow] = []
        for candle in candles:
            indicator_set = indicator_map.get(candle.open_time)
            if indicator_set is None:
                indicator_set = ComputedIndicatorSet(
                    symbol=candle.symbol,
                    interval=candle.interval,
                    open_time=candle.open_time,
                    values={},
                    is_ready=False,
                    missing_outputs=(),
                )
            rows.append(FeatureRow.from_components(candle, indicator_set))
        return rows

    def get_latest_complete_window(
        self,
        symbol: str,
        interval: str,
        window_size: int,
        required_features: tuple[str, ...],
    ) -> FeatureWindow | None:
        """Read the latest canonical feature window from stored candles and indicators."""
        normalized_symbol = normalize_symbol(symbol)
        latest_open_time = self.get_latest_candle_time(normalized_symbol, interval)
        if latest_open_time is None:
            return None

        interval_delta = interval_to_timedelta(interval)
        end_time = latest_open_time + interval_delta
        start_time = end_time - (interval_delta * window_size)
        candles = self.get_candles(normalized_symbol, interval, start_time, end_time)
        rows = self.get_feature_rows(normalized_symbol, interval, start_time, end_time)
        indicator_sets = self.get_indicator_batch(normalized_symbol, interval, start_time, end_time)

        if len(candles) != len(indicator_sets):
            return FeatureWindow(
                symbol=normalized_symbol,
                interval=interval,
                rows=tuple(rows),
                requested_features=required_features,
                is_complete=False,
                gap_reason=GAP_REASON_MISSING_DERIVED_ROWS,
            )

        return build_feature_window(
            rows,
            symbol=normalized_symbol,
            interval=interval,
            window_size=window_size,
            required_features=required_features,
        )

    def save_prediction_journal_entry(self, entry: PredictionJournalEntry) -> PredictionJournalEntry:
        """Insert or return one idempotent prediction journal row."""
        self._ensure_static_table(self._prediction_journal_model)
        now = datetime.now(UTC)
        payload = prediction_journal_to_record(entry)
        payload["created_at"] = entry.created_at or now
        payload["updated_at"] = now
        with self._session_factory() as session:
            existing_stmt = select(self._prediction_journal_model).where(
                self._prediction_journal_model.symbol == entry.symbol,
                self._prediction_journal_model.interval == entry.interval,
                self._prediction_journal_model.model_name == entry.model_name,
                self._prediction_journal_model.artifact_sha256 == entry.artifact_sha256,
                self._prediction_journal_model.reference_time == entry.reference_time,
                self._prediction_journal_model.prediction_time == entry.prediction_time,
            )
            existing = session.scalars(existing_stmt).first()
            if existing is not None:
                return existing.to_domain()
            row = self._prediction_journal_model(**payload)
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalars(existing_stmt).first()
                if existing is None:
                    raise
                return existing.to_domain()
            session.refresh(row)
            return row.to_domain()

    def get_unsettled_prediction_journal_entries(
        self,
        symbol: str,
        interval: str,
        until: datetime,
        limit: int = 1000,
    ) -> tuple[PredictionJournalEntry, ...]:
        """Return unsettled prediction rows ready for settlement."""
        self._ensure_static_table(self._prediction_journal_model)
        normalized_symbol = normalize_symbol(symbol)
        normalized_until = ensure_utc(until)
        with self._session_factory() as session:
            stmt = (
                select(self._prediction_journal_model)
                .where(
                    self._prediction_journal_model.symbol == normalized_symbol,
                    self._prediction_journal_model.interval == interval,
                    self._prediction_journal_model.prediction_time <= normalized_until,
                    self._prediction_journal_model.settled_at.is_(None),
                )
                .order_by(self._prediction_journal_model.prediction_time.asc())
                .limit(limit)
            )
            return tuple(row.to_domain() for row in session.scalars(stmt).all())

    def get_latest_prediction_journal_entries(
        self,
        symbol: str,
        interval: str,
        reference_time: datetime,
        stale_after: timedelta,
    ) -> tuple[PredictionJournalEntry, ...]:
        """Return the newest usable prediction rows grouped by model artifact."""
        self._ensure_static_table(self._prediction_journal_model)
        normalized_symbol = normalize_symbol(symbol)
        normalized_time = ensure_utc(reference_time)
        with self._session_factory() as session:
            stmt = (
                select(self._prediction_journal_model)
                .where(
                    self._prediction_journal_model.symbol == normalized_symbol,
                    self._prediction_journal_model.interval == interval,
                    self._prediction_journal_model.reference_time <= normalized_time,
                    self._prediction_journal_model.reference_time >= normalized_time - stale_after,
                )
                .order_by(self._prediction_journal_model.reference_time.desc())
            )
            rows = [row.to_domain() for row in session.scalars(stmt).all()]
        newest_by_artifact: dict[tuple[str, str], PredictionJournalEntry] = {}
        for row in rows:
            newest_by_artifact.setdefault((row.model_name, row.artifact_sha256), row)
        return tuple(newest_by_artifact.values())

    def list_recent_prediction_journal_entries(
        self,
        symbol: str,
        interval: str,
        limit: int = 20,
    ) -> tuple[PredictionJournalEntry, ...]:
        """Return recent prediction journal rows for observability."""
        self._ensure_static_table(self._prediction_journal_model)
        if limit < 1:
            raise ValueError("`limit` must be positive.")
        normalized_symbol = normalize_symbol(symbol)
        with self._session_factory() as session:
            stmt = (
                select(self._prediction_journal_model)
                .where(
                    self._prediction_journal_model.symbol == normalized_symbol,
                    self._prediction_journal_model.interval == interval,
                )
                .order_by(
                    self._prediction_journal_model.reference_time.desc(),
                    self._prediction_journal_model.created_at.desc(),
                    self._prediction_journal_model.id.desc(),
                )
                .limit(limit)
            )
            return tuple(row.to_domain() for row in session.scalars(stmt).all())

    def settle_prediction_journal_entry(self, settlement: PredictionJournalSettlement) -> PredictionJournalEntry:
        """Persist actual outcome fields for one journal entry."""
        self._ensure_static_table(self._prediction_journal_model)
        with self._session_factory() as session:
            row = session.get(self._prediction_journal_model, settlement.journal_id)
            if row is None:
                raise ValueError(f"Prediction journal entry {settlement.journal_id} was not found.")
            row.actual_value = settlement.actual_value
            row.actual_return = settlement.actual_return
            row.actual_direction = settlement.actual_direction
            row.absolute_error = settlement.absolute_error
            row.absolute_percentage_error = settlement.absolute_percentage_error
            row.direction_correct = settlement.direction_correct
            row.settled_at = settlement.settled_at
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return row.to_domain()

    def summarize_prediction_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
        model_name: str | None = None,
    ) -> PredictionJournalSummary:
        """Return aggregate journal metrics for one time range."""
        self._ensure_static_table(self._prediction_journal_model)
        normalized_symbol = normalize_symbol(symbol)
        normalized_start = ensure_utc(start_time)
        normalized_end = ensure_utc(end_time)
        with self._session_factory() as session:
            conditions = [
                self._prediction_journal_model.symbol == normalized_symbol,
                self._prediction_journal_model.interval == interval,
                self._prediction_journal_model.reference_time >= normalized_start,
                self._prediction_journal_model.reference_time < normalized_end,
            ]
            if model_name:
                conditions.append(self._prediction_journal_model.model_name == model_name.strip().lower())
            stmt = select(self._prediction_journal_model).where(*conditions)
            rows = [row.to_domain() for row in session.scalars(stmt).all()]

        settled = tuple(row for row in rows if row.settled_at is not None and row.actual_value is not None)
        predicted_values = tuple(row.predicted_value for row in settled)
        actual_values = tuple(float(row.actual_value) for row in settled)
        reference_values = tuple(row.reference_value for row in settled)
        predicted_returns = tuple(row.predicted_return for row in rows)
        actual_returns = tuple(float(row.actual_return) for row in settled if row.actual_return is not None)
        predicted_counts = self._direction_counts(row.predicted_direction for row in rows)
        actual_counts = self._direction_counts(row.actual_direction for row in settled if row.actual_direction)
        return PredictionJournalSummary(
            symbol=normalized_symbol,
            interval=interval,
            model_name=model_name.strip().lower() if model_name else None,
            start_time=normalized_start,
            end_time=normalized_end,
            prediction_count=len(rows),
            settled_count=len(settled),
            mape=mape(predicted_values, actual_values) if settled else None,
            rmse=rmse(predicted_values, actual_values) if settled else None,
            direction_accuracy=direction_accuracy(
                predicted_values=predicted_values,
                actual_values=actual_values,
                reference_values=reference_values,
            )
            if settled
            else None,
            mean_predicted_return=(sum(predicted_returns) / len(predicted_returns)) if predicted_returns else None,
            mean_actual_return=(sum(actual_returns) / len(actual_returns)) if actual_returns else None,
            predicted_direction_counts=predicted_counts,
            actual_direction_counts=actual_counts,
        )

    def save_agent_decision_journal_entry(self, entry: AgentDecisionJournalEntry) -> AgentDecisionJournalEntry:
        """Insert or return one idempotent agent decision journal row."""
        self._ensure_static_table(self._agent_decision_journal_model)
        now = datetime.now(UTC)
        payload = agent_decision_journal_to_record(entry)
        payload["created_at"] = entry.created_at or now
        payload["updated_at"] = now
        with self._session_factory() as session:
            existing_stmt = select(self._agent_decision_journal_model).where(
                self._agent_decision_journal_model.cycle_id == entry.cycle_id,
                self._agent_decision_journal_model.symbol == entry.symbol,
                self._agent_decision_journal_model.interval == entry.interval,
            )
            existing = session.scalars(existing_stmt).first()
            if existing is not None:
                return existing.to_domain()
            row = self._agent_decision_journal_model(**payload)
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalars(existing_stmt).first()
                if existing is None:
                    raise
                return existing.to_domain()
            session.refresh(row)
            return row.to_domain()

    def update_agent_decision_execution(
        self,
        journal_id: int,
        *,
        execution_status: str,
        exchange_response: dict[str, Any],
        exchange_order_id: str | None = None,
        exchange_client_order_id: str | None = None,
    ) -> AgentDecisionJournalEntry:
        """Persist the exchange result for one journaled decision."""
        self._ensure_static_table(self._agent_decision_journal_model)
        with self._session_factory() as session:
            row = session.get(self._agent_decision_journal_model, journal_id)
            if row is None:
                raise ValueError(f"Agent decision journal entry {journal_id} was not found.")
            row.execution_status = execution_status
            row.exchange_response = exchange_response
            row.exchange_order_id = exchange_order_id
            row.exchange_client_order_id = exchange_client_order_id
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return row.to_domain()

    def list_recent_agent_decision_journal_entries(
        self,
        symbol: str,
        interval: str,
        limit: int = 20,
    ) -> tuple[AgentDecisionJournalEntry, ...]:
        """Return recent agent decision rows for observability."""
        self._ensure_static_table(self._agent_decision_journal_model)
        if limit < 1:
            raise ValueError("`limit` must be positive.")
        normalized_symbol = normalize_symbol(symbol)
        with self._session_factory() as session:
            stmt = (
                select(self._agent_decision_journal_model)
                .where(
                    self._agent_decision_journal_model.symbol == normalized_symbol,
                    self._agent_decision_journal_model.interval == interval,
                )
                .order_by(
                    self._agent_decision_journal_model.reference_time.desc(),
                    self._agent_decision_journal_model.created_at.desc(),
                    self._agent_decision_journal_model.id.desc(),
                )
                .limit(limit)
            )
            return tuple(row.to_domain() for row in session.scalars(stmt).all())

    def summarize_agent_decision_journal(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime,
    ) -> AgentDecisionJournalSummary:
        """Return aggregate decision counts for one time range."""
        self._ensure_static_table(self._agent_decision_journal_model)
        normalized_symbol = normalize_symbol(symbol)
        normalized_start = ensure_utc(start_time)
        normalized_end = ensure_utc(end_time)
        with self._session_factory() as session:
            stmt = select(self._agent_decision_journal_model).where(
                self._agent_decision_journal_model.symbol == normalized_symbol,
                self._agent_decision_journal_model.interval == interval,
                self._agent_decision_journal_model.reference_time >= normalized_start,
                self._agent_decision_journal_model.reference_time < normalized_end,
            )
            rows = [row.to_domain() for row in session.scalars(stmt).all()]
        return AgentDecisionJournalSummary(
            symbol=normalized_symbol,
            interval=interval,
            start_time=normalized_start,
            end_time=normalized_end,
            decision_count=len(rows),
            action_counts=self._value_counts((row.action for row in rows), ("buy", "sell", "hold")),
            risk_status_counts=self._value_counts((row.risk_status for row in rows), ("approved", "rejected", "skipped")),
            execution_status_counts=self._value_counts(
                (row.execution_status for row in rows),
                ("not_submitted", "submitted", "filled", "partially_filled", "cancelled", "rejected", "failed"),
            ),
            mode_counts=self._value_counts((row.mode for row in rows), ("dry_run", "spot_demo")),
        )

    def get_operational_risk_snapshot(self, symbol: str, at: datetime) -> OperationalRiskSnapshot:
        """Build daily execution controls from persisted filled Spot Demo orders."""
        self._ensure_static_table(self._agent_decision_journal_model)
        normalized_symbol = normalize_symbol(symbol)
        normalized_at = ensure_utc(at)
        day_start = normalized_at.replace(hour=0, minute=0, second=0, microsecond=0)
        with self._session_factory() as session:
            stmt = (
                select(self._agent_decision_journal_model)
                .where(
                    self._agent_decision_journal_model.mode == "spot_demo",
                    self._agent_decision_journal_model.symbol == normalized_symbol,
                    self._agent_decision_journal_model.exchange_order_id.is_not(None),
                    self._agent_decision_journal_model.created_at <= normalized_at,
                )
                .order_by(self._agent_decision_journal_model.created_at.asc())
            )
            rows = session.scalars(stmt).all()

        inventory_quantity = 0.0
        inventory_cost = 0.0
        realized_pnl_today = 0.0
        orders_today = 0
        last_order_at = None
        for row in rows:
            created_at = ensure_utc(row.created_at)
            order = self._resolved_exchange_order(row.exchange_response)
            if not order:
                continue
            executed_quantity = float(order.get("executedQty", 0) or 0)
            quote_quantity = float(order.get("cummulativeQuoteQty", 0) or 0)
            if executed_quantity <= 0 or quote_quantity <= 0:
                continue
            if created_at >= day_start:
                orders_today += 1
            last_order_at = created_at
            if str(order.get("side", row.action)).lower() == "buy":
                inventory_quantity += executed_quantity
                inventory_cost += quote_quantity
                continue
            if inventory_quantity <= 0:
                continue
            sold_quantity = min(executed_quantity, inventory_quantity)
            allocated_cost = inventory_cost * (sold_quantity / inventory_quantity)
            realized_pnl = (quote_quantity * (sold_quantity / executed_quantity)) - allocated_cost
            if created_at >= day_start:
                realized_pnl_today += realized_pnl
            inventory_quantity -= sold_quantity
            inventory_cost -= allocated_cost

        return OperationalRiskSnapshot(
            orders_today=orders_today,
            realized_pnl_today_usdt=realized_pnl_today,
            observed_at=normalized_at,
            last_order_at=last_order_at,
            position_quantity=inventory_quantity,
            position_cost_usdt=inventory_cost,
        )

    @staticmethod
    def _resolved_exchange_order(exchange_response: dict[str, Any]) -> dict[str, Any]:
        """Return the newest order payload persisted by execution reconciliation."""
        if not exchange_response:
            return {}
        reconciliation = exchange_response.get("reconciliation")
        if isinstance(reconciliation, dict):
            return reconciliation
        submission = exchange_response.get("submission")
        if isinstance(submission, dict):
            return submission
        return exchange_response

    @staticmethod
    def _direction_counts(values: Iterable[str | None]) -> dict[str, int]:
        counts = {"up": 0, "down": 0, "flat": 0}
        for value in values:
            if value in counts:
                counts[value] += 1
        return counts

    @staticmethod
    def _value_counts(values: Iterable[str], allowed: tuple[str, ...]) -> dict[str, int]:
        counts = {value: 0 for value in allowed}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts

    @contextmanager
    def cycle_lock(self, lock_key: str):
        """Acquire one PostgreSQL advisory lock for the duration of an agent cycle."""
        with self._session_factory() as session:
            acquired = bool(
                session.scalar(
                    text("SELECT pg_try_advisory_lock(hashtext(:lock_key))"),
                    {"lock_key": lock_key},
                )
            )
            try:
                yield acquired
            finally:
                if acquired:
                    session.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:lock_key))"),
                        {"lock_key": lock_key},
                    )
