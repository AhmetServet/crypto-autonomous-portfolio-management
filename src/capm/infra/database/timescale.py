"""PostgreSQL/TimescaleDB repository implementations using SQLAlchemy."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import create_engine, delete, inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import sessionmaker

from capm.domains.market_data.entities import OHLCV, ensure_utc
from capm.infra.database.models import candle_to_record, get_ohlcv_model


class TimescaleMarketDataRepository:
    """PostgreSQL + TimescaleDB SQLAlchemy implementation for OHLCV storage."""

    def __init__(self, connection_string: str, schema_name: str | None = None) -> None:
        """Initialize the repository by creating the SQLAlchemy engine.
        
        Example connection_string: 'postgresql+psycopg://user:password@localhost:5432/capm_db'
        """
        # Ensure we use psycopg 3 dialect for SQLAlchemy if plain 'postgresql://' is passed.
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg://", 1)
            
        self._engine = create_engine(connection_string)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False)
        self._schema_name = (
            schema_name.strip() if schema_name and self._engine.dialect.name == "postgresql" else None
        )
        self._initialized_tables: set[str] = set()

    def initialize_schema(self, symbols: Iterable[str] | None = None) -> None:
        """Create symbol-scoped tables and execute TimescaleDB hypertable setup."""
        if self._engine.dialect.name == "postgresql":
            self._ensure_timescale_extension()
            self._ensure_schema_exists()
        for symbol in symbols or []:
            self._ensure_table(symbol)

    def _ensure_timescale_extension(self) -> None:
        """Install the TimescaleDB extension when PostgreSQL is used."""
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))

    def _ensure_schema_exists(self) -> None:
        """Create the configured schema if it does not already exist."""
        if not self._schema_name:
            return
        with self._engine.begin() as conn:
            quoted_schema_name = conn.dialect.identifier_preparer.quote_identifier(
                self._schema_name
            )
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

    def _get_existing_model(self, symbol: str):
        """Return the symbol model only if the backing table already exists."""
        model = get_ohlcv_model(symbol, self._schema_name)
        if not inspect(self._engine).has_table(model.__tablename__, schema=self._schema_name):
            return None
        self._initialized_tables.add(model.__tablename__)
        return model

    def _ensure_table(self, symbol: str):
        """Create the table for a symbol on first use."""
        model = get_ohlcv_model(symbol, self._schema_name)
        table_name = model.__tablename__
        if table_name in self._initialized_tables:
            return model

        model.__table__.create(self._engine, checkfirst=True)
        if self._engine.dialect.name == "postgresql":
            self._ensure_hypertable(table_name)
        self._initialized_tables.add(table_name)
        return model

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Create or update a batch of OHLCV candles to TimescaleDB.
        
        Uses PostgreSQL "UPSERT" feature (ON CONFLICT DO UPDATE).
        """
        if not candles:
            return

        candles_by_symbol: dict[str, list[OHLCV]] = defaultdict(list)
        for candle in candles:
            candles_by_symbol[candle.symbol].append(candle)

        for symbol, symbol_candles in candles_by_symbol.items():
            model = self._ensure_table(symbol)
            with self._session_factory() as session:
                if self._engine.dialect.name == "postgresql":
                    values = [candle_to_record(candle) for candle in symbol_candles]
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
                    for candle in symbol_candles:
                        session.merge(model.from_domain(candle))
                session.commit()

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the open_time of the latest stored candle for a symbol and interval."""
        model = self._get_existing_model(symbol)
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
        model = self._get_existing_model(symbol)
        if model is None:
            return []
        with self._session_factory() as session:
            stmt = (
                select(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time
                )
                .order_by(model.open_time.asc())
            )
            results = session.scalars(stmt).all()
            return [model.to_domain() for model in results]

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        """Read a single precise candle based on its composite primary key."""
        model = self._get_existing_model(symbol)
        if model is None:
            return None
        with self._session_factory() as session:
            stmt = select(model).where(
                model.interval == interval,
                model.open_time == open_time
            )
            result = session.scalars(stmt).first()
            return result.to_domain() if result else None

    def delete_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> int:
        """Delete candles for a given symbol, interval, and time window. Returns number of rows deleted."""
        model = self._get_existing_model(symbol)
        if model is None:
            return 0
        with self._session_factory() as session:
            stmt = (
                delete(model)
                .where(
                    model.interval == interval,
                    model.open_time >= start_time,
                    model.open_time < end_time
                )
            )
            result = session.execute(stmt)
            session.commit()
            return int(result.rowcount or 0)

