"""Database bootstrap entrypoint for CAPM."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from capm.core.config import DatabaseSettings
from capm.infra.database.timescale import TimescaleMarketDataRepository


def initialize_database(symbols: Sequence[str] | None = None) -> TimescaleMarketDataRepository:
    """Initialize CAPM schema objects inside the configured database."""
    database_settings = DatabaseSettings.from_env()

    repository = TimescaleMarketDataRepository(
        database_settings.connection_string,
        schema_name=database_settings.schema_name,
    )
    repository.initialize_schema(symbols)
    return repository


def build_parser() -> argparse.ArgumentParser:
    """Build the database bootstrap argument parser."""
    parser = argparse.ArgumentParser(prog="capm-init-db")
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Trading pair to initialize as a dedicated table, e.g. BTCUSDT.",
    )
    return parser


def main() -> None:
    """Bootstrap the configured CAPM schema and optional symbol tables."""
    args = build_parser().parse_args()
    database_settings = DatabaseSettings.from_env()
    repository = initialize_database(args.symbol)
    initialized = ", ".join(args.symbol) if args.symbol else "no symbol tables"
    print(
        "Schema bootstrap completed for "
        f"{database_settings.schema_name} in "
        f"{repository._engine.url.database or 'configured database'} with {initialized}."
    )


if __name__ == "__main__":
    main()
