"""PostgreSQL/TimescaleDB repository implementations."""

from __future__ import annotations

from datetime import datetime
import json

import psycopg
from psycopg.types.json import Jsonb

from capm.domains.market_data.entities import OHLCV


class TimescaleMarketDataRepository:
    """PostgreSQL + TimescaleDB implementation for OHLCV storage."""

    def __init__(self, connection_string: str) -> None:
        """Initialize the repository with a connection string.
        
        Example: 'postgresql://user:password@localhost:5432/capm_db'
        """
        self._conn_string = connection_string

    def initialize_schema(self) -> None:
        """Create the table and TimescaleDB hypertable if they do not exist."""
        # Note: Requires TimescaleDB extension to be installed in the database:
        # CREATE EXTENSION IF NOT EXISTS timescaledb;
        
        table_query = """
        CREATE TABLE IF NOT EXISTS ohlcv (
            symbol VARCHAR(20) NOT NULL,
            interval VARCHAR(5) NOT NULL,
            open_time TIMESTAMPTZ NOT NULL,
            close_time TIMESTAMPTZ NOT NULL,
            open NUMERIC NOT NULL,
            high NUMERIC NOT NULL,
            low NUMERIC NOT NULL,
            close NUMERIC NOT NULL,
            volume NUMERIC NOT NULL,
            quote_asset_volume NUMERIC NOT NULL,
            trade_count INTEGER NOT NULL,
            taker_buy_base_asset_volume NUMERIC NOT NULL,
            taker_buy_quote_asset_volume NUMERIC NOT NULL,
            PRIMARY KEY (symbol, interval, open_time)
        );
        """
        
        hypertable_query = """
        SELECT create_hypertable(
            'ohlcv', 
            'open_time', 
            chunk_time_interval => INTERVAL '7 days', 
            if_not_exists => TRUE
        );
        """
        with psycopg.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(table_query)
                cur.execute(hypertable_query)
            conn.commit()

    def save_ohlcv_batch(self, candles: list[OHLCV]) -> None:
        """Save a batch of OHLCV candles to TimescaleDB.
        
        Uses fast COPY or execute_many under the hood depending on psycopg v3 optimizations.
        """
        if not candles:
            return

        query = """
        INSERT INTO ohlcv (
            symbol, interval, open_time, close_time, open, high, low, close, 
            volume, quote_asset_volume, trade_count, taker_buy_base_asset_volume, taker_buy_quote_asset_volume
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        ) ON CONFLICT (symbol, interval, open_time) DO UPDATE SET
            close_time = EXCLUDED.close_time,
            open = EXCLUDED.open,
            high = EXCLUDED.high,
            low = EXCLUDED.low,
            close = EXCLUDED.close,
            volume = EXCLUDED.volume,
            quote_asset_volume = EXCLUDED.quote_asset_volume,
            trade_count = EXCLUDED.trade_count,
            taker_buy_base_asset_volume = EXCLUDED.taker_buy_base_asset_volume,
            taker_buy_quote_asset_volume = EXCLUDED.taker_buy_quote_asset_volume;
        """

        # Prepare data tuple-list
        data = [
            (
                c.symbol, c.interval, c.open_time, c.close_time, 
                c.open, c.high, c.low, c.close,
                c.volume, c.quote_asset_volume, c.trade_count,
                c.taker_buy_base_asset_volume, c.taker_buy_quote_asset_volume
            )
            for c in candles
        ]

        with psycopg.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.executemany(query, data)
            conn.commit()

    def get_latest_candle_time(self, symbol: str, interval: str) -> datetime | None:
        """Get the open_time of the latest stored candle for a symbol and interval."""
        query = """
        SELECT MAX(open_time) 
        FROM ohlcv 
        WHERE symbol = %s AND interval = %s;
        """
        with psycopg.connect(self._conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(query, (symbol, interval))
                result = cur.fetchone()
                return result[0] if result else None
