"""PostgreSQL/TimescaleDB repository implementations using SQLAlchemy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from itertools import islice
from typing import Any

from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from capm.domains.features import (
    ComputedIndicatorSet,
    FeatureRow,
    FeatureWindow,
    GAP_REASON_MISSING_DERIVED_ROWS,
    build_feature_window,
)
from capm.domains.market_data import interval_to_timedelta, normalize_symbol
from capm.domains.market_data.entities import OHLCV, ensure_utc
from capm.infra.database.models import (
    candle_to_record,
    get_feature_model,
    get_ohlcv_model,
    indicator_to_record,
)


class TimescaleMarketDataRepository:
    """SQLAlchemy repository for raw OHLCV candles and derived feature rows."""

    def __init__(
        self,
        connection_string: str,
        schema_name: str | None = None,
        *,
        feature_write_batch_size: int = 1000,
    ) -> None:
        """Initialize the repository by creating the SQLAlchemy engine."""
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg://", 1)

        self._engine = create_engine(connection_string, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False)
        self._schema_name = (
            schema_name.strip() if schema_name and self._engine.dialect.name == "postgresql" else None
        )
        self._feature_write_batch_size = feature_write_batch_size
        self._initialized_tables: set[str] = set()

    def initialize_schema(self, symbols: Iterable[str] | None = None) -> None:
        """Create symbol-scoped market and feature tables."""
        if self._engine.dialect.name == "postgresql":
            self._ensure_timescale_extension()
            self._ensure_schema_exists()
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

    def _ensure_hypertable(self, table_name: str) -> None:
        """Convert a symbol table into a TimescaleDB hypertable."""
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

    def _get_existing_model(self, symbol: str, model_factory: Callable[[str, str | None], Any]):
        """Return a dynamic model only if its backing table exists."""
        model = model_factory(symbol, self._schema_name)
        if not inspect(self._engine).has_table(model.__tablename__, schema=self._schema_name):
            return None
        self._initialized_tables.add(model.__tablename__)
        return model

    def _ensure_table(self, symbol: str, model_factory: Callable[[str, str | None], Any]):
        """Create a symbol-scoped table on first use."""
        model = model_factory(symbol, self._schema_name)
        table_name = model.__tablename__
        if table_name in self._initialized_tables:
            return model

        model.__table__.create(self._engine, checkfirst=True)
        if self._engine.dialect.name == "postgresql":
            self._ensure_hypertable(table_name)
        self._initialized_tables.add(table_name)
        return model

    def _get_existing_market_model(self, symbol: str):
        """Return the OHLCV model if its table exists."""
        return self._get_existing_model(symbol, get_ohlcv_model)

    def _ensure_market_table(self, symbol: str):
        """Create the OHLCV table for a symbol on first use."""
        return self._ensure_table(symbol, get_ohlcv_model)

    def _get_existing_feature_model(self, symbol: str):
        """Return the feature model if its table exists."""
        return self._get_existing_model(symbol, get_feature_model)

    def _ensure_feature_table(self, symbol: str):
        """Create the feature table for a symbol on first use."""
        return self._ensure_table(symbol, get_feature_model)

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
            for batch in self._batched(symbol_records, batch_size):
                with self._session_factory() as session:
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

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Create or update a batch of OHLCV candles."""
        if not candles:
            return

        candles_by_symbol: dict[str, list[OHLCV]] = defaultdict(list)
        for candle in candles:
            candles_by_symbol[candle.symbol].append(candle)

        self._save_records(
            records_by_symbol=candles_by_symbol,
            model_resolver=self._ensure_market_table,
            payload_builder=candle_to_record,
        )

    def save_indicator_batch(self, records: list[ComputedIndicatorSet]) -> None:
        """Create or update a batch of derived indicator rows."""
        if not records:
            return

        records_by_symbol: dict[str, list[ComputedIndicatorSet]] = defaultdict(list)
        for record in records:
            records_by_symbol[record.symbol].append(record)

        self._save_records(
            records_by_symbol=records_by_symbol,
            model_resolver=self._ensure_feature_table,
            payload_builder=indicator_to_record,
            batch_size=self._feature_write_batch_size,
        )

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
            results = session.scalars(stmt).all()
            return [result.to_domain() for result in results]

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
            results = session.scalars(stmt).all()
            return [result.to_domain() for result in results]

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
