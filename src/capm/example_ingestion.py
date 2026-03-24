"""Example script to demonstrate Binance ingestion -> TimescaleDB storage."""

import os
from datetime import datetime, timedelta

from capm.core.config.settings import Settings
from capm.domains.market_data import HistoricalOHLCRequest
from capm.infra.exchange.binance_spot import BinanceSpotMarketDataRestAdapter
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.ingestion.historical import HistoricalMarketDataIngestionService


def run_ingestion() -> None:
    """Run an example ingestion process."""
    # 1. Altyapı bileşenlerini (Adapters & Repositories) ayağa kaldır
    settings = Settings()
    binance_adapter = BinanceSpotMarketDataRestAdapter(settings=settings)
    
    # Kendi veritabanı bağlantı dizginizi buraya girin (örnek)
    # Şifreyi veya kullanıcıyı kendi sisteminizdeki ile değiştirin.
    db_conn_string = os.getenv(
        "DATABASE_URL", 
        "postgresql://postgres:postgres@localhost:5432/capm_db"
    )
    db_repo = TimescaleMarketDataRepository(db_conn_string)
    
    # İlk kullanımda veritabanı tablolarını ve Timescale eklentisini ayarlar
    print("Veritabanı tabloları kontrol ediliyor...")
    db_repo.initialize_schema()

    # 2. Servisi (Usecase) oluştur (Dependency Injection)
    ingestion_service = HistoricalMarketDataIngestionService(
        market_data_port=binance_adapter,
        repository_port=db_repo  # Veriler artık veritabanına da kaydedilecek
    )

    # 3. İsteği hazırla: BTC/USDT'nin son 1 saatteki 1 dakikalık mumları
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=1)
    
    request = HistoricalOHLCRequest(
        symbol="BTCUSDT",
        interval="1m",
        start_at=start_time,
        end_at=end_time,
        max_records_per_page=1000
    )

    print(f"{request.symbol} için {request.start_at} ile {request.end_at} arası veriler çekiliyor...")
    
    # 4. İşlemi çalıştır
    candles = ingestion_service.fetch_ohlcv(request)
    
    print(f"Başarılı! Toplam {len(candles)} adet mum çekildi ve TimescaleDB'ye kaydedildi.")
    
    # Veritabanında kayıtlı son mumu kontrol edelim:
    latest_time = db_repo.get_latest_candle_time("BTCUSDT", "1m")
    print(f"Veritabanındaki en güncel BTCUSDT 1m mumu tarihi: {latest_time}")


if __name__ == "__main__":
    run_ingestion()
