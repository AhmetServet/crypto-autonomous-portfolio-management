"""PostgreSQL/TimescaleDB repository implementations using SQLAlchemy."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, select, delete, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from capm.domains.market_data.entities import OHLCV
from capm.infra.database.models import Base, OHLCVModel


class TimescaleMarketDataRepository:
    """PostgreSQL + TimescaleDB SQLAlchemy implementation for OHLCV storage."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the repository by creating the SQLAlchemy engine.
        
        Example connection_string: 'postgresql+psycopg://user:password@localhost:5432/capm_db'
        """
        # Ensure we use psycopg 3 dialect for SQLAlchemy if plain 'postgresql://' is passed.
        if connection_string.startswith("postgresql://"):
            connection_string = connection_string.replace("postgresql://", "postgresql+psycopg://", 1)
            
        self._engine = create_engine(connection_string)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False)

    def initialize_schema(self) -> None:
        """Create the tables via SQLAlchemy and execute TimescaleDB hypertable setup."""
        # Create all tables according to SQLAlchemy metadata
        Base.metadata.create_all(bind=self._engine)
        
        # Setup TimescaleDB specific hypertable
        hypertable_query = """
        SELECT create_hypertable(
            'ohlcv', 
            'open_time', 
            chunk_time_interval => INTERVAL '7 days', 
            if_not_exists => TRUE
        );
        """
        with self._engine.begin() as conn:
            # We must use text() to execute raw SQL in SQLAlchemy
            conn.execute(text(hypertable_query))

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Create or update a batch of OHLCV candles to TimescaleDB.
        
        Uses PostgreSQL "UPSERT" feature (ON CONFLICT DO UPDATE).
        """
        if not candles:
            return

        with self._session_factory() as session:
            # Convert domain entities to bulk insert dictionaries
            values = [OHLCVModel.from_domain(c).__dict__ for c in candles]
            # Strip out internal SQLAlchemy state
            for v in values:
                v.pop("_sa_instance_state", None)

            stmt = pg_insert(OHLCVModel).values(values)
            
            # On conflict (matching symbol, interval, open_time), update everything else.
            # This is essential for backfilling partial candles incrementally (e.g. streaming overrides).
            update_dict = {
                c.name: c for c in stmt.excluded 
                if c.name not in ['symbol', 'interval', 'open_time']
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=['symbol', 'interval', 'open_time'],
                set_=update_dict
            )

            session.execute(stmt)
            session.commit()

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Read the open_time of the latest stored candle for a symbol and interval."""
        with self._session_factory() as session:
            stmt = (
                select(OHLCVModel.open_time)
                .where(OHLCVModel.symbol == symbol, OHLCVModel.interval == interval)
                .order_by(OHLCVModel.open_time.desc())
                .limit(1)
            )
            return session.scalar(stmt)

    def get_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> list[OHLCV]:
        """Read candles for a given symbol, interval, and exact time window [start_time, end_time)."""
        with self._session_factory() as session:
            stmt = (
                select(OHLCVModel)
                .where(
                    OHLCVModel.symbol == symbol,
                    OHLCVModel.interval == interval,
                    OHLCVModel.open_time >= start_time,
                    OHLCVModel.open_time < end_time
                )
                .order_by(OHLCVModel.open_time.asc())
            )
            results = session.scalars(stmt).all()
            return [model.to_domain() for model in results]

    def get_candle(self, symbol: str, interval: str, open_time: datetime) -> OHLCV | None:
        """Read a single precise candle based on its composite primary key."""
        with self._session_factory() as session:
            stmt = select(OHLCVModel).where(
                OHLCVModel.symbol == symbol,
                OHLCVModel.interval == interval,
                OHLCVModel.open_time == open_time
            )
            result = session.scalar(stmt)
            return result.to_domain() if result else None

    def delete_candles(self, symbol: str, interval: str, start_time: datetime, end_time: datetime) -> int:
        """Delete candles for a given symbol, interval, and time window. Returns number of rows deleted."""
        with self._session_factory() as session:
            stmt = (
                delete(OHLCVModel)
                .where(
                    OHLCVModel.symbol == symbol,
                    OHLCVModel.interval == interval,
                    OHLCVModel.open_time >= start_time,
                    OHLCVModel.open_time < end_time
                )
            )
            result = session.execute(stmt)
            session.commit()
            return result.rowcount

