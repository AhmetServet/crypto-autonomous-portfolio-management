"""One closed-candle trading cycle for daytime Spot Demo operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import subprocess
import sys
from typing import Callable

from capm.domains.features import IndicatorSpec
from capm.domains.market_data import HistoricalOHLCRequest, interval_to_timedelta
from capm.domains.trading import RiskConfig
from capm.services.features import IndicatorPipelineService
from capm.services.ingestion import HistoricalMarketDataIngestionService
from capm.services.prediction_journal import PredictionJournalService


def default_live_indicator_specs() -> tuple[IndicatorSpec, ...]:
    """Return the persisted indicator set used by trained production artifacts."""
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


@dataclass(frozen=True, slots=True)
class LiveCycleResult:
    """Auditable summary for one attempted closed-candle cycle."""

    cycle_time: datetime
    symbols: tuple[str, ...]
    ingested_candles: int
    persisted_indicators: int
    predictions_journaled: int
    predictions_settled: int
    decisions: tuple
    skipped_reason: str | None = None


@dataclass(slots=True)
class LiveTradingCycleService:
    """Refresh market state, journal predictions, then run one LLM decision batch."""

    repository: object
    market_data_adapter: object
    trading_agent: object
    llm_policy: object
    artifacts_by_symbol: dict[str, tuple[Path, ...]]
    indicator_specs: tuple[IndicatorSpec, ...] = ()
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    max_inline_gap_minutes: int = 180
    max_model_age_days: int = 3
    allow_large_gap_recovery: bool = False
    allow_stale_models: bool = False
    prediction_runner: Callable[[Path, str, str, datetime], None] | None = None
    risk_config: RiskConfig | None = None

    def run_once(self, *, interval: str = "1m", mode: str = "dry_run") -> LiveCycleResult:
        """Run one idempotent cycle using only fully closed candles."""
        if self.max_inline_gap_minutes < 1:
            raise ValueError("max_inline_gap_minutes must be positive.")
        if self.max_model_age_days < 1:
            raise ValueError("max_model_age_days must be positive.")
        interval_delta = interval_to_timedelta(interval)
        cycle_time = self._floor_to_interval(self.now(), interval_delta)
        lock_key = f"capm:live-cycle:{interval}:{cycle_time.isoformat()}"
        with self.repository.cycle_lock(lock_key) as acquired:
            if not acquired:
                return LiveCycleResult(
                    cycle_time=cycle_time,
                    symbols=(),
                    ingested_candles=0,
                    persisted_indicators=0,
                    predictions_journaled=0,
                    predictions_settled=0,
                    decisions=(),
                    skipped_reason="cycle_lock_not_acquired",
                )
            return self._run_locked(cycle_time=cycle_time, interval=interval, mode=mode)

    def _run_locked(self, *, cycle_time: datetime, interval: str, mode: str) -> LiveCycleResult:
        interval_delta = interval_to_timedelta(interval)
        symbols = self.repository.get_available_symbols(interval)
        if not symbols:
            raise ValueError(f"No stored candles exist for interval {interval}.")
        missing_artifacts = tuple(symbol for symbol in symbols if not self.artifacts_by_symbol.get(symbol))
        if missing_artifacts:
            raise ValueError(f"No production model artifacts configured for symbols: {list(missing_artifacts)}.")
        self._validate_artifact_freshness(cycle_time)

        ingestion = HistoricalMarketDataIngestionService(
            market_data_port=self.market_data_adapter,
            repository_port=self.repository,
        )
        indicator_pipeline = IndicatorPipelineService(
            market_data_repository=self.repository,
            feature_repository=self.repository,
            feature_window_reader=self.repository,
        )
        prediction_journal = PredictionJournalService(
            journal_repository=self.repository,
            market_data_repository=self.repository,
        )
        specs = self.indicator_specs or default_live_indicator_specs()
        ingested_candles = 0
        persisted_indicators = 0
        predictions_journaled = 0
        predictions_settled = 0

        for symbol in symbols:
            latest_candle_time = self.repository.get_latest_candle_time(symbol, interval)
            if latest_candle_time is None:
                raise ValueError(f"No stored candle exists for {symbol} {interval}.")
            ingest_start = latest_candle_time + interval_delta
            large_gap_recovery_start = None
            if ingest_start < cycle_time:
                missing_candles = int((cycle_time - ingest_start) / interval_delta)
                gap_minutes = int((cycle_time - ingest_start).total_seconds() / 60)
                if gap_minutes > self.max_inline_gap_minutes and not self.allow_large_gap_recovery:
                    raise ValueError(
                        f"{symbol} has {missing_candles} missing {interval} candles across {gap_minutes} minute(s). "
                        f"Inline recovery limit is {self.max_inline_gap_minutes} minute(s). "
                        "Run an explicit OHLCV and indicator recovery first, or rerun with "
                        "--allow-large-gap-recovery."
                    )
                if gap_minutes > self.max_inline_gap_minutes:
                    large_gap_recovery_start = ingest_start
                ingestion_result = ingestion.ingest_ohlcv(
                    HistoricalOHLCRequest(
                        symbol=symbol,
                        interval=interval,
                        start_at=ingest_start,
                        end_at=cycle_time,
                    )
                )
                ingested_candles += ingestion_result.stored_count

            latest_candle_time = self.repository.get_latest_candle_time(symbol, interval)
            if latest_candle_time is None:
                raise ValueError(f"No stored candle exists for {symbol} {interval} after ingestion.")
            if latest_candle_time + interval_delta != cycle_time:
                raise ValueError(
                    f"Latest closed candle for {symbol} is {latest_candle_time.isoformat()}, "
                    f"expected {(cycle_time - interval_delta).isoformat()}."
                )

            max_lookback = max(spec.required_lookback for spec in specs)
            indicator_start = latest_candle_time - (interval_delta * max(max_lookback * 2, 100))
            if large_gap_recovery_start is not None:
                indicator_start = large_gap_recovery_start - (interval_delta * (max_lookback - 1))
            batch = indicator_pipeline.compute_feature_batch(
                symbol=symbol,
                interval=interval,
                start_time=indicator_start,
                end_time=cycle_time,
                indicator_specs=specs,
            )
            persisted_indicators += len(batch.indicator_sets)

            settlement = prediction_journal.settle_predictions(
                symbol=symbol,
                interval=interval,
                until=cycle_time,
            )
            predictions_settled += settlement["settled"]
            for artifact_path in self.artifacts_by_symbol[symbol]:
                self._journal_prediction(artifact_path, symbol, interval, latest_candle_time)
                predictions_journaled += 1

        decisions = self.trading_agent.run_llm_once(
            interval=interval,
            mode=mode,
            llm_policy=self.llm_policy,
            risk_config=self.risk_config,
        )
        return LiveCycleResult(
            cycle_time=cycle_time,
            symbols=symbols,
            ingested_candles=ingested_candles,
            persisted_indicators=persisted_indicators,
            predictions_journaled=predictions_journaled,
            predictions_settled=predictions_settled,
            decisions=decisions,
        )

    def _journal_prediction(
        self,
        artifact_path: Path,
        symbol: str,
        interval: str,
        reference_time: datetime,
    ) -> None:
        if self.prediction_runner is not None:
            self.prediction_runner(artifact_path, symbol, interval, reference_time)
            return
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "capm.predict_worker",
                    "--model-artifact",
                    str(artifact_path),
                    "--symbol",
                    symbol,
                    "--interval",
                    interval,
                    "--at",
                    reference_time.isoformat(),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Prediction worker failed for {symbol} artifact {artifact_path}: {exc.stderr.strip()}"
            ) from exc

    def _validate_artifact_freshness(self, cycle_time: datetime) -> None:
        if self.allow_stale_models:
            return
        oldest_allowed = cycle_time - timedelta(days=self.max_model_age_days)
        stale = []
        for symbol, artifact_paths in self.artifacts_by_symbol.items():
            for artifact_path in artifact_paths:
                if not artifact_path.is_file():
                    raise FileNotFoundError(f"Model artifact not found: {artifact_path}")
                modified_at = datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=UTC)
                if modified_at < oldest_allowed:
                    stale.append(f"{symbol}={artifact_path} modified_at={modified_at.isoformat()}")
        if stale:
            raise ValueError(
                f"Production model artifacts are older than {self.max_model_age_days} day(s): {stale}. "
                "Train fresh production models first, or rerun with --allow-stale-models for an explicit "
                "non-production recovery check."
            )

    @staticmethod
    def _floor_to_interval(value: datetime, interval_delta) -> datetime:
        normalized = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
        seconds = int(interval_delta.total_seconds())
        floored_timestamp = int(normalized.timestamp()) // seconds * seconds
        return datetime.fromtimestamp(floored_timestamp, tz=UTC)
