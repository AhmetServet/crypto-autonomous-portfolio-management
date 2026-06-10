"""Request schemas for the dashboard API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SpotDemoMarketBuyRequest(BaseModel):
    """Manual Spot Demo market-buy request."""

    symbol: str = Field(default="BTCUSDT", min_length=1)
    usdt_amount: float = Field(gt=0)
    confirm: bool = False


class SpotDemoMarketSellRequest(BaseModel):
    """Manual Spot Demo market-sell request."""

    symbol: str = Field(default="BTCUSDT", min_length=1)
    quantity: float = Field(gt=0)
    confirm: bool = False


class LiveCycleRunOnceRequest(BaseModel):
    """Request body for one closed-candle agent cycle."""

    interval: str = Field(default="1m", min_length=1)
    mode: str = Field(default="dry-run", pattern="^(dry-run|spot-demo)$")
    model_artifacts: list[str] = Field(min_length=1)
    market_data_mode: str = Field(default="demo", pattern="^(demo|live)$")
    max_inline_gap_minutes: int = Field(default=180, ge=1)
    max_model_age_days: int = Field(default=3, ge=1)
    allow_large_gap_recovery: bool = False
    allow_stale_models: bool = False
    max_trade_usdt: float = Field(default=25.0, gt=0)
    max_position_usdt: float = Field(default=100.0, gt=0)
    emergency_stop: bool = False
    max_daily_realized_loss_usdt: float = Field(default=50.0, gt=0)
    max_orders_per_day: int = Field(default=20, ge=1)
    order_cooldown_minutes: int = Field(default=5, ge=0)
    max_total_exposure_usdt: float = Field(default=100.0, gt=0)


class LiveCycleLoopRequest(LiveCycleRunOnceRequest):
    """Request body for a dashboard-managed continuous agent loop."""

    cycle_offset_seconds: float = Field(default=2.0, ge=0)
    max_cycles: int | None = Field(default=None, ge=1)
    stop_after_error_count: int = Field(default=3, ge=1)
    sleep_after_error_seconds: float = Field(default=10.0, ge=0)
    name: str | None = None


class InitDatabaseRequest(BaseModel):
    """Initialize database metadata and optional symbol tables."""

    symbols: list[str] = Field(default_factory=list)


class FetchOHLCVRequest(BaseModel):
    """Fetch historical candles, optionally persisting missing rows."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    mode: str = Field(default="demo", pattern="^(demo|live)$")
    persist: bool = False
    batch_size: int = Field(default=10_000, ge=1)


class IngestOHLCVRequest(BaseModel):
    """Ingest OHLCV candles from REST or public dumps."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    source: str = Field(default="dump-with-rest-tail", pattern="^(rest|dump|dump-with-rest-tail)$")
    mode: str = Field(default="live", pattern="^(demo|live)$")
    batch_size: int = Field(default=50_000, ge=1)


class RepairOHLCVGapsRequest(BaseModel):
    """Repair missing OHLCV coverage gaps inside a requested range."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    mode: str = Field(default="demo", pattern="^(demo|live)$")
    batch_size: int = Field(default=50_000, ge=1)


class BackfillIndicatorsRequest(BaseModel):
    """Compute and persist indicator rows for stored candles."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    chunk_candle_count: int = Field(default=10_000, ge=1)
    resume_from_latest: bool = True


class ModelArtifactStateRequest(BaseModel):
    """Update dashboard registry state for a local model artifact."""

    artifact_path: str = Field(min_length=1)
    active: bool | None = None
    archived: bool | None = None
    notes: str | None = None


class TrainingJobRequest(BaseModel):
    """Start a dashboard-managed model training job."""

    training_type: str = Field(pattern="^(tabular|deep_learning|statistical)$")
    config: dict[str, Any] = Field(default_factory=dict)
    name: str | None = None


class PredictRequest(BaseModel):
    """Run one persisted model artifact against DB-backed data."""

    model_artifact: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    at: str | None = None
    journal: bool = False


class PredictBatchRequest(BaseModel):
    """Run multiple persisted model artifacts against DB-backed data."""

    model_artifacts: list[str] = Field(min_length=1)
    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    at: str | None = None
    journal: bool = False


class SettlePredictionsRequest(BaseModel):
    """Settle prediction journal rows whose target candles are available."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    until: str | None = None
    limit: int = Field(default=1000, ge=1)


class JournalSummaryRequest(BaseModel):
    """Summarize prediction or agent journal rows."""

    symbol: str = Field(min_length=1)
    interval: str = Field(default="1m", min_length=1)
    start: str = Field(min_length=1)
    end: str = Field(min_length=1)
    model_name: str | None = None


class AgentRunOnceRequest(BaseModel):
    """Run one threshold or LLM policy trading-agent cycle."""

    symbol: str | None = None
    interval: str = Field(default="1m", min_length=1)
    mode: str = Field(default="dry-run", pattern="^(dry-run|spot-demo)$")
    policy: str = Field(default="threshold", pattern="^(threshold|llm)$")
    show_prompt: bool = False
    dry_run_usdt_balance: float = Field(default=1000.0, ge=0)
    dry_run_base_asset_balance: float = Field(default=0.0, ge=0)
    max_trade_usdt: float = Field(default=25.0, gt=0)
    max_position_usdt: float = Field(default=100.0, gt=0)
    min_predicted_return: float = 0.0005
    prediction_staleness_minutes: int = Field(default=5, ge=1)
    emergency_stop: bool = False
    max_daily_realized_loss_usdt: float = Field(default=50.0, gt=0)
    max_orders_per_day: int = Field(default=20, ge=1)
    order_cooldown_minutes: int = Field(default=5, ge=0)
    max_total_exposure_usdt: float = Field(default=100.0, gt=0)
