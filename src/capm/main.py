"""Composition root and CLI entrypoint for CAPM."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from capm.core.config import BinanceSettings
from capm.domains.market_data import HistoricalOHLCRequest
from capm.infra.exchange import BinanceSpotMarketDataAdapter
from capm.services.ingestion import HistoricalMarketDataIngestionService


def parse_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def fetch_ohlcv(
    *,
    symbol: str,
    interval: str,
    start_at: datetime,
    end_at: datetime,
    mode: str = "demo",
) -> list[dict[str, str | int]]:
    """Fetch historical OHLCV candles from Binance spot."""
    settings = BinanceSettings.from_env(mode=mode)
    adapter = BinanceSpotMarketDataAdapter(settings=settings)
    service = HistoricalMarketDataIngestionService(market_data_port=adapter)

    try:
        candles = service.fetch_ohlcv(
            HistoricalOHLCRequest(
                symbol=symbol,
                interval=interval,
                start_at=start_at,
                end_at=end_at,
            )
        )
        return [candle.to_dict() for candle in candles]
    finally:
        adapter.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the CAPM CLI argument parser."""
    parser = argparse.ArgumentParser(prog="capm")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch-ohlc",
        help="Fetch historical OHLCV candles from Binance spot.",
    )
    fetch_parser.add_argument("--symbol", required=True, help="Trading pair, e.g. BTC/USDT.")
    fetch_parser.add_argument("--interval", required=True, help="Binance kline interval.")
    fetch_parser.add_argument(
        "--start",
        required=True,
        help="Inclusive start datetime in ISO-8601 format.",
    )
    fetch_parser.add_argument(
        "--end",
        required=True,
        help="Exclusive end datetime in ISO-8601 format.",
    )
    fetch_parser.add_argument(
        "--mode",
        default="demo",
        choices=["demo", "live"],
        help="Binance environment to query.",
    )

    return parser


def main() -> None:
    """Run the CAPM CLI."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "fetch-ohlc":
        candles = fetch_ohlcv(
            symbol=args.symbol,
            interval=args.interval,
            start_at=parse_datetime(args.start),
            end_at=parse_datetime(args.end),
            mode=args.mode,
        )
        print(json.dumps(candles, indent=2))
