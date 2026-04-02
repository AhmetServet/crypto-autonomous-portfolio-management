"""SQLAlchemy ORM model factory for symbol-scoped market and feature tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from typing import Any, cast

from sqlalchemy import Boolean, DateTime, Integer, JSON, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from capm.domains.features import ComputedIndicatorSet
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
_FEATURE_MODEL_CACHE: dict[tuple[str | None, str], type[Base]] = {}


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


def _serialize_indicator_values(values: dict[str, Decimal | None]) -> dict[str, str | None]:
    """Convert indicator values into JSON-friendly storage payloads."""
    return {
        name: None if value is None else str(value)
        for name, value in values.items()
    }


def _deserialize_indicator_values(payload: dict[str, object] | None) -> dict[str, Decimal | None]:
    """Convert a stored payload back into domain indicator values."""
    if not payload:
        return {}

    values: dict[str, Decimal | None] = {}
    for name, raw_value in payload.items():
        values[name] = None if raw_value is None else Decimal(str(raw_value))
    return values


class FeatureModelMixin:
    """Shared behavior for dynamically generated feature models."""

    __symbol__: str

    @property
    def symbol(self) -> str:
        """Expose the symbol implied by the table name."""
        return type(self).__symbol__

    def to_domain(self) -> ComputedIndicatorSet:
        """Convert the SQLAlchemy model to a computed indicator record."""
        return ComputedIndicatorSet(
            symbol=self.symbol,
            interval=self.interval,
            open_time=ensure_utc(self.open_time),
            values=_deserialize_indicator_values(self.feature_payload),
            is_ready=self.is_ready,
            missing_outputs=tuple(self.missing_outputs or []),
        )

    @classmethod
    def from_domain(cls, entity: ComputedIndicatorSet) -> Any:
        """Convert a computed indicator record into a SQLAlchemy model."""
        if normalize_symbol(entity.symbol) != cls.__symbol__:
            raise ValueError(
                f"Expected indicator row for table {cls.__symbol__!r}, got {entity.symbol!r}."
            )
        return cls(
            interval=entity.interval,
            open_time=entity.open_time,
            is_ready=entity.is_ready,
            feature_payload=_serialize_indicator_values(entity.values),
            missing_outputs=list(entity.missing_outputs),
        )


def indicator_to_record(entity: ComputedIndicatorSet) -> dict[str, object]:
    """Convert a computed indicator row into a database record payload."""
    return {
        "interval": entity.interval,
        "open_time": entity.open_time,
        "is_ready": entity.is_ready,
        "feature_payload": _serialize_indicator_values(entity.values),
        "missing_outputs": list(entity.missing_outputs),
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


def get_feature_model(symbol: str, schema_name: str | None = None) -> type[Base]:
    """Return a cached ORM model for the given normalized symbol feature table."""
    normalized_symbol = normalize_symbol(symbol)
    cache_key = (schema_name, normalized_symbol)
    cached_model = _FEATURE_MODEL_CACHE.get(cache_key)
    if cached_model is not None:
        return cached_model

    table_name = f"{normalized_symbol}_features"
    annotations = {
        "interval": Mapped[str],
        "open_time": Mapped[datetime],
        "is_ready": Mapped[bool],
        "feature_payload": Mapped[dict[str, object]],
        "missing_outputs": Mapped[list[str]],
    }
    attributes: dict[str, Any] = {
        "__tablename__": table_name,
        "__module__": __name__,
        "__symbol__": normalized_symbol,
        "__table_args__": {"schema": schema_name} if schema_name else {},
        "__annotations__": annotations,
        "interval": mapped_column(String(5), primary_key=True),
        "open_time": mapped_column(DateTime(timezone=True), primary_key=True),
        "is_ready": mapped_column(Boolean, nullable=False, default=False),
        "feature_payload": mapped_column(JSON, nullable=False, default=dict),
        "missing_outputs": mapped_column(JSON, nullable=False, default=list),
    }

    model = cast(
        type[Base],
        type(f"{normalized_symbol}FeatureModel", (FeatureModelMixin, Base), attributes),
    )
    _FEATURE_MODEL_CACHE[cache_key] = model
    return model