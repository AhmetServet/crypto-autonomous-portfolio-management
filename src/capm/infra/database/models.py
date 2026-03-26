"""SQLAlchemy ORM models for market data."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, DateTime, String, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from capm.domains.market_data.entities import OHLCV


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


class OHLCVModel(Base):
    """SQLAlchemy model mapping for the OHLCV domain entity."""
    
    __tablename__ = "ohlcv"
    
    # TimescaleDB requires the time column to be part of any unique/primary key constraint usually,
    # and partitioning revolves around time.
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(5), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    
    close_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    open: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    quote_asset_volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False)
    taker_buy_base_asset_volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    taker_buy_quote_asset_volume: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    def to_domain(self) -> OHLCV:
        """Convert the SQLAlchemy model to a cross-layer domain entity."""
        return OHLCV(
            symbol=self.symbol,
            interval=self.interval,
            open_time=self.open_time,
            close_time=self.close_time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            quote_asset_volume=self.quote_asset_volume,
            trade_count=self.trade_count,
            taker_buy_base_asset_volume=self.taker_buy_base_asset_volume,
            taker_buy_quote_asset_volume=self.taker_buy_quote_asset_volume,
        )

    @classmethod
    def from_domain(cls, entity: OHLCV) -> "OHLCVModel":
        """Convert a cross-layer domain entity into a SQLAlchemy model."""
        return cls(
            symbol=entity.symbol,
            interval=entity.interval,
            open_time=entity.open_time,
            close_time=entity.close_time,
            open=entity.open,
            high=entity.high,
            low=entity.low,
            close=entity.close,
            volume=entity.volume,
            quote_asset_volume=entity.quote_asset_volume,
            trade_count=entity.trade_count,
            taker_buy_base_asset_volume=entity.taker_buy_base_asset_volume,
            taker_buy_quote_asset_volume=entity.taker_buy_quote_asset_volume,
        )