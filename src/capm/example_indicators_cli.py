"""End-to-end example that persists one year of indicators to the database."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from capm.core.config.settings import BinanceSettings
from capm.domains.features import IndicatorSpec
from capm.domains.market_data import HistoricalOHLCRequest, normalize_symbol
from capm.infra.exchange.binance_spot import BinanceSpotMarketDataAdapter
from capm.init_db import initialize_database
from capm.services.features import IndicatorPipelineService
from capm.services.ingestion import HistoricalMarketDataIngestionService


def _print_fetch_progress(completed_days: int, total_days: int, at: datetime) -> None:
    """Show one-line fetch progress (overwrites the same line)."""
    print(
        f"\rFetch: {completed_days}/{total_days} days completed (through {at:%Y-%m-%d %H:%M}Z)",
        end="",
        flush=True,
    )


def build_indicator_specs() -> tuple[IndicatorSpec, ...]:
    """Return the built-in indicators used in the end-to-end example."""
    return (
        IndicatorSpec(name="", kind="sma", parameters={"period": 20}),
        IndicatorSpec(name="", kind="ema", parameters={"period": 20}),
        IndicatorSpec(name="", kind="rsi", parameters={"period": 14}),
        IndicatorSpec(
            name="",
            kind="macd",
            parameters={"fast_period": 12, "slow_period": 26, "signal_period": 9},
        ),
        IndicatorSpec(
            name="",
            kind="bbands",
            parameters={"period": 20, "stddev_multiplier": "2"},
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the one-year indicator example."""
    parser = argparse.ArgumentParser(prog="python -m capm.example_indicators_1y")
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="Trading pair to test end to end, e.g. BTC/USDT.",
    )
    parser.add_argument(
        "--mode",
        default="demo",
        choices=["demo", "live"],
        help="Binance environment to use.",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=5,
        help="Number of rows to read back from the stored feature window.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="How many days of 1m candles to backfill.",
    )
    parser.add_argument(
        "--chunk-candle-count",
        type=int,
        default=10000,
        help="How many candles to compute and persist per feature chunk.",
    )
    return parser


def run_indicator_example_1y(
    *,
    symbol: str,
    mode: str,
    window_size: int,
    days: int,
    chunk_candle_count: int,
) -> None:
    """Fetch a long range of candles, persist indicators in chunks, and read the latest stored window."""
    normalized_symbol = normalize_symbol(symbol)
    interval = "1m"
    end_time = datetime.now(UTC).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(days=days)

    print(f"Initializing database objects for {normalized_symbol}...")
    repository = initialize_database([normalized_symbol])

    print(f"Preparing Binance {mode} client...")
    settings = BinanceSettings.from_env(mode=mode)
    adapter = BinanceSpotMarketDataAdapter(settings=settings)
    ingestion_service = HistoricalMarketDataIngestionService(
        market_data_port=adapter,
        repository_port=repository,
    )
    request = HistoricalOHLCRequest(
        symbol=normalized_symbol,
        interval=interval,
        start_at=start_time,
        end_at=end_time,
    )

    print(
        f"Fetching and storing {days} day(s) of {interval} candles for {normalized_symbol} "
        f"from {start_time.isoformat()} to {end_time.isoformat()}..."
    )
    try:
        candles = ingestion_service.fetch_ohlcv(request, on_fetch_progress=_print_fetch_progress)
    finally:
        adapter.close()

    print()
    fetched_count = len(candles)
    del candles
    print(f"Stored {fetched_count} raw candles in the database.")

    indicator_service = IndicatorPipelineService(
        market_data_repository=repository,
        feature_repository=repository,
        feature_window_reader=repository,
    )
    specs = build_indicator_specs()

    def print_progress(chunk) -> None:
        """Print incremental backfill progress."""
        print(
            f"Chunk {chunk.chunk_index}: "
            f"{chunk.chunk_start_time.isoformat()} -> {chunk.chunk_end_time.isoformat()} | "
            f"candles={chunk.candles_read} persisted={chunk.indicator_rows_persisted}"
        )

    print("Computing and persisting indicator rows in chunks...")
    backfill = indicator_service.backfill_feature_range(
        symbol=normalized_symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        indicator_specs=specs,
        chunk_candle_count=chunk_candle_count,
        resume_from_latest=True,
        progress_callback=print_progress,
    )

    print("Reading the latest stored feature window...")
    window = indicator_service.get_latest_window(
        symbol=normalized_symbol,
        interval=interval,
        end_time=end_time,
        window_size=window_size,
        indicator_specs=specs,
    )

    latest_indicator_time = repository.get_latest_indicator_time(normalized_symbol, interval)
    latest_indicator = (
        repository.get_indicator_set(normalized_symbol, interval, latest_indicator_time)
        if latest_indicator_time is not None
        else None
    )

    if backfill.resumed_from is not None:
        print(f"Resumed from latest persisted indicator timestamp: {backfill.resumed_from.isoformat()}")
    print(f"Feature chunks processed: {backfill.chunks_processed}")
    print(f"Feature backfill candles read: {backfill.candles_read}")
    print(f"Stored {backfill.indicator_rows_persisted} indicator rows in feature tables.")
    print(f"Latest complete window: {window.is_complete}")
    print(f"Window size returned: {window.window_size}")
    if latest_indicator is not None:
        print(f"Latest persisted indicator timestamp: {latest_indicator.open_time.isoformat()}")
        print(f"Latest persisted row ready: {latest_indicator.is_ready}")
        if latest_indicator.missing_outputs:
            print(f"Latest persisted missing outputs: {', '.join(latest_indicator.missing_outputs)}")

    if window.rows:
        latest_row = window.rows[-1]
        print(f"Latest feature row timestamp: {latest_row.open_time.isoformat()}")
        print("Latest indicator values:")
        for name, value in sorted(latest_row.indicator_values.items()):
            print(f"  {name}: {value}")


def main() -> None:
    """Run the one-year end-to-end indicator example."""
    args = build_parser().parse_args()
    run_indicator_example_1y(
        symbol=args.symbol,
        mode=args.mode,
        window_size=args.window_size,
        days=args.days,
        chunk_candle_count=args.chunk_candle_count,
    )


if __name__ == "__main__":
    main()
