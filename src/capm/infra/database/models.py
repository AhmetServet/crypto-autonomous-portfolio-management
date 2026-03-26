"""SQLAlchemy ORM model factory for symbol-scoped market data tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from capm.domains.market_data.entities import OHLCV, ensure_utc, normalize_symbol


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


class OHLCVModelMixin:
    """Shared behavior for dynamically generated OHLCV models."""

    __symbol__: str

    @property
    def symbol(self) -> str:
        """Expose the symbol implied by the table name."""
        return type(self).__symbol__

    def to_domain(self) -> OHLCV:
        """Convert the SQLAlchemy model to a cross-layer domain entity."""
        return OHLCV(
            symbol=self.symbol,
            interval=self.interval,
            open_time=ensure_utc(self.open_time),
            close_time=ensure_utc(self.close_time),
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
    def from_domain(cls, entity: OHLCV) -> Any:
        """Convert a cross-layer domain entity into a SQLAlchemy model."""
        if normalize_symbol(entity.symbol) != cls.__symbol__:
            raise ValueError(
                f"Expected candle for table {cls.__symbol__!r}, got {entity.symbol!r}."
            )
        return cls(
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


_OHLCV_MODEL_CACHE: dict[tuple[str | None, str], type[Base]] = {}


def candle_to_record(entity: OHLCV) -> dict[str, object]:
    """Convert a candle into a database record payload."""
    return {
        "interval": entity.interval,
        "open_time": entity.open_time,
        "close_time": entity.close_time,
        "open": entity.open,
        "high": entity.high,
        "low": entity.low,
        "close": entity.close,
        "volume": entity.volume,
        "quote_asset_volume": entity.quote_asset_volume,
        "trade_count": entity.trade_count,
        "taker_buy_base_asset_volume": entity.taker_buy_base_asset_volume,
        "taker_buy_quote_asset_volume": entity.taker_buy_quote_asset_volume,
    }


def get_ohlcv_model(symbol: str, schema_name: str | None = None) -> type[Base]:
    """Return a cached ORM model for the given normalized symbol."""
    normalized_symbol = normalize_symbol(symbol)
    cache_key = (schema_name, normalized_symbol)
    cached_model = _OHLCV_MODEL_CACHE.get(cache_key)
    if cached_model is not None:
        return cached_model

    annotations = {
        "interval": Mapped[str],
        "open_time": Mapped[datetime],
        "close_time": Mapped[datetime],
        "open": Mapped[Decimal],
        "high": Mapped[Decimal],
        "low": Mapped[Decimal],
        "close": Mapped[Decimal],
        "volume": Mapped[Decimal],
        "quote_asset_volume": Mapped[Decimal],
        "trade_count": Mapped[int],
        "taker_buy_base_asset_volume": Mapped[Decimal],
        "taker_buy_quote_asset_volume": Mapped[Decimal],
    }
    attributes: dict[str, Any] = {
        "__tablename__": normalized_symbol,
        "__module__": __name__,
        "__symbol__": normalized_symbol,
        "__table_args__": {"schema": schema_name} if schema_name else {},
        "__annotations__": annotations,
        "interval": mapped_column(String(5), primary_key=True),
        "open_time": mapped_column(DateTime(timezone=True), primary_key=True),
        "close_time": mapped_column(DateTime(timezone=True), nullable=False),
        "open": mapped_column(Numeric, nullable=False),
        "high": mapped_column(Numeric, nullable=False),
        "low": mapped_column(Numeric, nullable=False),
        "close": mapped_column(Numeric, nullable=False),
        "volume": mapped_column(Numeric, nullable=False),
        "quote_asset_volume": mapped_column(Numeric, nullable=False),
        "trade_count": mapped_column(Integer, nullable=False),
        "taker_buy_base_asset_volume": mapped_column(Numeric, nullable=False),
        "taker_buy_quote_asset_volume": mapped_column(Numeric, nullable=False),
    }

    model = cast(
        type[Base],
        type(f"{normalized_symbol}OHLCVModel", (OHLCVModelMixin, Base), attributes),
    )
    _OHLCV_MODEL_CACHE[cache_key] = model
    return model