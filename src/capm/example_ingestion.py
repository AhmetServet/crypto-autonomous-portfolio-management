"""Example script to demonstrate Binance ingestion -> TimescaleDB storage."""

from datetime import datetime, timedelta, timezone

from capm.core.config.settings import BinanceSettings
from capm.domains.market_data import HistoricalOHLCRequest
from capm.infra.exchange.binance_spot import BinanceSpotMarketDataAdapter
from capm.init_db import initialize_database
from capm.services.ingestion.historical import HistoricalMarketDataIngestionService


def run_ingestion() -> None:
    """Run an example ingestion process."""
    # 1. Build adapters and repositories from environment-backed settings.
    exchange_settings = BinanceSettings.from_env(mode="demo")
    binance_adapter = BinanceSpotMarketDataAdapter(settings=exchange_settings)

    # 2. Prepare the request for the last hour of BTCUSDT 1m candles.
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=1)
    request = HistoricalOHLCRequest(
        symbol="BTCUSDT",
        interval="1m",
        start_at=start_time,
        end_at=end_time,
        max_records_per_page=1000,
    )

    print("Schema bootstrap is being prepared...")
    db_repo = initialize_database([request.symbol])

    # 3. Build the service via dependency injection.
    ingestion_service = HistoricalMarketDataIngestionService(
        market_data_port=binance_adapter,
        repository_port=db_repo,
    )

    print(f"Fetching candles for {request.symbol} from {request.start_at} to {request.end_at}...")

    # 4. Execute the ingestion flow.
    candles = ingestion_service.fetch_ohlcv(request)

    print(f"Success: fetched and stored {len(candles)} candles in the {request.symbol} table.")

    latest_time = db_repo.get_latest_candle_time(request.symbol, request.interval)
    print(f"Latest stored {request.symbol} {request.interval} candle open_time: {latest_time}")


if __name__ == "__main__":
    run_ingestion()
