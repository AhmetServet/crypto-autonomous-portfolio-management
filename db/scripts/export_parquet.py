#!/usr/bin/env python3
"""Export CAPM DB tables to separate Parquet files.

Example:
    uv run --with pandas --with pyarrow python db/scripts/export_parquet.py \
      --symbol BTCUSDT \
      --interval 1m \
      --start 2021-05-26T00:00:00Z \
      --end 2026-06-13T00:00:00Z
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


DEFAULT_OUTPUT_ROOT = Path("db/exports")
DEFAULT_SCHEMA = "capm"
COVERAGE_TABLES = ("ohlcv_coverage", "indicator_coverage", "feature_coverage")


def parse_datetime(value: str | None) -> datetime | None:
    """Parse an optional ISO-8601 datetime and normalize it to UTC."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def quote_identifier(value: str) -> str:
    """Quote one SQL identifier."""
    return '"' + value.replace('"', '""') + '"'


def qualified_table(schema_name: str | None, table_name: str) -> str:
    """Return a schema-qualified table name."""
    quoted_table = quote_identifier(table_name)
    if schema_name:
        return f"{quote_identifier(schema_name)}.{quoted_table}"
    return quoted_table


def load_parquet_dependencies() -> tuple[Any, Any, Any]:
    """Load optional export dependencies with actionable failure text."""
    try:
        import pandas as pd
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Missing export deps. Run with: "
            "uv run --with pandas --with pyarrow python db/scripts/export_parquet.py ..."
        ) from exc
    return pd, pa, pq


def resolve_connection_string() -> str:
    """Read DB URL from env."""
    connection_string = (os.getenv("CAPM_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if not connection_string:
        raise ValueError("Set CAPM_DATABASE_URL or DATABASE_URL, or pass --env-file with one of them.")
    if connection_string.startswith("postgresql://"):
        return connection_string.replace("postgresql://", "postgresql+psycopg://", 1)
    return connection_string


def resolve_coinpair(connection, *, schema_name: str | None, symbol: str) -> dict[str, object]:
    """Resolve symbol to id-scoped OHLCV and feature tables."""
    row = connection.execute(
        text(
            f"""
            SELECT id, symbol
            FROM {qualified_table(schema_name, "coinpairs")}
            WHERE symbol = :symbol
            """
        ),
        {"symbol": symbol},
    ).mappings().first()
    if row is None:
        raise ValueError(f"Symbol {symbol!r} not found in coinpairs.")
    coinpair_id = int(row["id"])
    return {
        "id": coinpair_id,
        "symbol": row["symbol"],
        "ohlcv_table": f"coinpair_{coinpair_id}_ohlcv",
        "feature_table": f"coinpair_{coinpair_id}_feature",
    }


def numeric_expr(dialect_name: str, column_name: str) -> str:
    """Return a portable-enough numeric-to-float SQL expression."""
    quoted = quote_identifier(column_name)
    if dialect_name == "postgresql":
        return f"{quoted}::double precision AS {quoted}"
    return f"CAST({quoted} AS REAL) AS {quoted}"


def json_text_expr(dialect_name: str, column_name: str, alias: str) -> str:
    """Return JSON payload as text for stable Parquet writing."""
    quoted = quote_identifier(column_name)
    quoted_alias = quote_identifier(alias)
    if dialect_name == "postgresql":
        return f"{quoted}::text AS {quoted_alias}"
    return f"CAST({quoted} AS TEXT) AS {quoted_alias}"


def write_query_to_parquet(
    *,
    connection,
    query: str,
    parameters: dict[str, object],
    output_path: Path,
    chunk_size: int,
) -> int:
    """Stream SQL query rows into one Parquet file."""
    pd, pa, pq = load_parquet_dependencies()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = None
    row_count = 0
    try:
        for frame in pd.read_sql_query(
            text(query),
            connection,
            params=parameters,
            chunksize=chunk_size,
        ):
            table = pa.Table.from_pandas(frame, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(output_path, table.schema)
            writer.write_table(table)
            row_count += len(frame)
    finally:
        if writer is not None:
            writer.close()
    if writer is None:
        pq.write_table(pa.Table.from_pandas(pd.DataFrame(), preserve_index=False), output_path)
    return row_count


def build_exports(
    *,
    schema_name: str | None,
    dialect_name: str,
    binding: dict[str, object],
    include_coverage: bool,
    include_not_ready_features: bool,
    has_start: bool,
    has_end: bool,
) -> dict[str, tuple[str, dict[str, object]]]:
    """Build export queries keyed by output filename."""
    ohlcv_table = qualified_table(schema_name, str(binding["ohlcv_table"]))
    feature_table = qualified_table(schema_name, str(binding["feature_table"]))
    coinpairs_table = qualified_table(schema_name, "coinpairs")
    start_filter = "AND open_time >= :start" if has_start else ""
    end_filter = "AND open_time < :end" if has_end else ""
    coverage_start_filter = "AND end_open_time >= :start" if has_start else ""
    coverage_end_filter = "AND start_open_time < :end" if has_end else ""
    ready_filter = "" if include_not_ready_features else "AND is_ready = true"

    numeric_columns = (
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "taker_buy_base_asset_volume",
        "taker_buy_quote_asset_volume",
    )
    ohlcv_numeric_select = ",\n                    ".join(numeric_expr(dialect_name, name) for name in numeric_columns)

    exports: dict[str, tuple[str, dict[str, object]]] = {
        "coinpairs.parquet": (
            f"""
            SELECT id, symbol
            FROM {coinpairs_table}
            WHERE symbol = :symbol
            ORDER BY id
            """,
            {"symbol": str(binding["symbol"])},
        ),
        f"{binding['ohlcv_table']}.parquet": (
            f"""
            SELECT
                interval,
                open_time,
                close_time,
                {ohlcv_numeric_select},
                trade_count
            FROM {ohlcv_table}
            WHERE interval = :interval
            {start_filter}
            {end_filter}
            ORDER BY open_time
            """,
            {},
        ),
        f"{binding['feature_table']}.parquet": (
            f"""
            SELECT
                interval,
                open_time,
                is_ready,
                {json_text_expr(dialect_name, "feature_payload", "feature_payload_json")},
                {json_text_expr(dialect_name, "missing_outputs", "missing_outputs_json")}
            FROM {feature_table}
            WHERE interval = :interval
            {ready_filter}
            {start_filter}
            {end_filter}
            ORDER BY open_time
            """,
            {},
        ),
    }

    if include_coverage:
        for coverage_table in COVERAGE_TABLES:
            table = qualified_table(schema_name, coverage_table)
            exports[f"{coverage_table}.parquet"] = (
                f"""
                SELECT id, coinpair_id, table_name, symbol, interval, start_open_time, end_open_time
                FROM {table}
                WHERE symbol = :symbol
                  AND interval = :interval
                {coverage_start_filter}
                {coverage_end_filter}
                ORDER BY start_open_time
                """,
                {},
            )
    return exports


def run(args: argparse.Namespace) -> dict[str, object]:
    """Run export and return metadata."""
    load_dotenv(args.env_file, override=False)
    schema_name = (args.schema or os.getenv("CAPM_DATABASE_SCHEMA") or DEFAULT_SCHEMA).strip() or None
    symbol = args.symbol.strip().upper()
    start = parse_datetime(args.start)
    end = parse_datetime(args.end)
    if start and end and start >= end:
        raise ValueError("--start must be before --end.")

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT_ROOT / f"{symbol.lower()}_{args.interval}"
    engine = create_engine(resolve_connection_string(), pool_pre_ping=True, hide_parameters=True)
    base_parameters = {
        "symbol": symbol,
        "interval": args.interval,
        "start": start,
        "end": end,
    }

    files: list[dict[str, object]] = []
    with engine.connect() as connection:
        binding = resolve_coinpair(connection, schema_name=schema_name, symbol=symbol)
        inspector = inspect(connection)
        expected_tables = ["coinpairs", str(binding["ohlcv_table"]), str(binding["feature_table"])]
        if args.include_coverage:
            expected_tables.extend(COVERAGE_TABLES)
        for table_name in expected_tables:
            if not inspector.has_table(table_name, schema=schema_name):
                raise ValueError(f"Required table {table_name!r} does not exist.")

        exports = build_exports(
            schema_name=schema_name,
            dialect_name=engine.dialect.name,
            binding=binding,
            include_coverage=args.include_coverage,
            include_not_ready_features=args.include_not_ready_features,
            has_start=start is not None,
            has_end=end is not None,
        )
        for filename, (query, extra_parameters) in exports.items():
            output_path = output_dir / filename
            row_count = write_query_to_parquet(
                connection=connection,
                query=query,
                parameters={**base_parameters, **extra_parameters},
                output_path=output_path,
                chunk_size=args.chunk_size,
            )
            files.append({"path": str(output_path), "rows": row_count})

    metadata = {
        "symbol": symbol,
        "interval": args.interval,
        "schema": schema_name,
        "start": args.start,
        "end": args.end,
        "coinpair_id": binding["id"],
        "ohlcv_table": binding["ohlcv_table"],
        "feature_table": binding["feature_table"],
        "include_not_ready_features": args.include_not_ready_features,
        "include_coverage": args.include_coverage,
        "exported_at": datetime.now(UTC).isoformat(),
        "files": files,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Export CAPM DB tables to Parquet.")
    parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
    parser.add_argument("--interval", required=True, help="Candle interval, e.g. 1m.")
    parser.add_argument("--start", default=None, help="Optional inclusive ISO-8601 start time.")
    parser.add_argument("--end", default=None, help="Optional exclusive ISO-8601 end time.")
    parser.add_argument("--output", default=None, help="Output dir. Default: db/exports/<symbol>_<interval>.")
    parser.add_argument("--env-file", default=".env", help="Dotenv file with CAPM_DATABASE_URL.")
    parser.add_argument("--schema", default=None, help="DB schema. Default: CAPM_DATABASE_SCHEMA or capm.")
    parser.add_argument("--chunk-size", type=int, default=100_000, help="Rows per DB read.")
    parser.add_argument(
        "--include-not-ready-features",
        action="store_true",
        help="Include feature rows where is_ready=false.",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_false",
        dest="include_coverage",
        help="Skip ohlcv_coverage, indicator_coverage, feature_coverage exports.",
    )
    parser.set_defaults(include_coverage=True)
    return parser


def main() -> None:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args()
    if args.chunk_size < 1:
        parser.error("--chunk-size must be greater than zero")
    try:
        metadata = run(args)
    except Exception as exc:
        raise SystemExit(f"export failed: {exc}") from exc
    print(json.dumps({"status": "ok", "export": metadata}, indent=2, default=str))


if __name__ == "__main__":
    main()
