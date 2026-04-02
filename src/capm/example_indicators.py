"""Example script to demonstrate DB-backed indicator persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from capm.core.config.settings import BinanceSettings
from capm.domains.features import IndicatorSpec
from capm.domains.market_data import HistoricalOHLCRequest, normalize_symbol
from capm.infra.exchange.binance_spot import BinanceSpotMarketDataAdapter
from capm.init_db import initialize_database
from capm.services.features import IndicatorPipelineService
from capm.services.ingestion import HistoricalMarketDataIngestionService


def run_indicator_example() -> None:
    """Fetch candles, persist indicators, and print the latest stored feature window."""
    symbol = normalize_symbol("BTC/USDT")
    interval = "1m"
    settings = BinanceSettings.from_env(mode="demo")
    adapter = BinanceSpotMarketDataAdapter(settings=settings)
    repository = initialize_database([symbol])
    ingestion_service = HistoricalMarketDataIngestionService(
        market_data_port=adapter,
        repository_port=repository,
    )

    end_time = datetime.now(UTC).replace(second=0, microsecond=0)
    start_time = end_time - timedelta(hours=2)
    request = HistoricalOHLCRequest(
        symbol=symbol,
        interval=interval,
        start_at=start_time,
        end_at=end_time,
    )

    try:
        candles = ingestion_service.fetch_ohlcv(request)
    finally:
        adapter.close()

    indicator_service = IndicatorPipelineService(
        market_data_repository=repository,
        feature_repository=repository,
        feature_window_reader=repository,
    )
    specs = (
        IndicatorSpec(name="", kind="sma", parameters={"period": 20}),
        IndicatorSpec(name="", kind="ema", parameters={"period": 20}),
        IndicatorSpec(name="", kind="rsi", parameters={"period": 14}),
        IndicatorSpec(name="", kind="macd", parameters={"fast_period": 12, "slow_period": 26, "signal_period": 9}),
        IndicatorSpec(name="", kind="bbands", parameters={"period": 20, "stddev_multiplier": "2"}),
    )
    batch = indicator_service.compute_feature_batch(
        symbol=symbol,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        indicator_specs=specs,
    )
    window = indicator_service.get_latest_window(
        symbol=symbol,
        interval=interval,
        end_time=end_time,
        window_size=5,
        indicator_specs=specs,
    )

    latest_indicator_time = repository.get_latest_indicator_time(symbol, interval)
    latest_indicator = (
        repository.get_indicator_set(symbol, interval, latest_indicator_time)
        if latest_indicator_time is not None
        else None
    )

    print(f"Fetched and stored {len(candles)} raw candles for {symbol}.")
    print(f"Computed and stored {len(batch.indicator_sets)} indicator rows.")
    print(f"Window complete: {window.is_complete}")
    print(f"Rows returned: {window.window_size}")
    if latest_indicator is not None:
        print(f"Latest stored indicator timestamp: {latest_indicator.open_time.isoformat()}")
        print(f"Latest row ready: {latest_indicator.is_ready}")
    if window.rows:
        latest = window.rows[-1]
        print(f"Latest candle open_time: {latest.open_time.isoformat()}")
        print("Latest indicators:")
        for name, value in sorted(latest.indicator_values.items()):
            print(f"  {name}: {value}")


if __name__ == "__main__":
    run_indicator_example()
