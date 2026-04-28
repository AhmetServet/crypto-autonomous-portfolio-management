"""CLI: run a walk-forward forecasting experiment from a JSON config file."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Any

from capm.core.config import DatabaseSettings
from capm.core.errors import ConfigurationError
from capm.domains.prediction import ForecastRequest, ForecastResult, ThresholdSignalPolicy
from capm.init_db import initialize_database
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.backtesting import BacktraderBacktestRunner
from capm.services.training import LocalArtifactStore, PredictionDatasetLoader, WalkForwardExperimentRunner


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _emit_progress(message: str, progress_callback: Any | None) -> None:
    if progress_callback is not None:
        progress_callback(message)


def build_progress_logger(*, enabled: bool) -> Any | None:
    """Return a stderr logger for human-readable progress updates."""
    if not enabled:
        return None

    def _log(message: str) -> None:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)

    return _log


def merge_forecast_results(results: Sequence[ForecastResult]) -> ForecastResult:
    """Concatenate per-split forecast results for strategy evaluation."""
    if not results:
        raise ValueError("At least one ForecastResult is required.")
    base = results[0]
    key = (base.symbol, base.interval, base.model_name, base.forecast_horizon)
    prediction_times: list[datetime] = []
    predicted_values: list[float] = []
    actual_values: list[float] = []
    reference_values: list[float] = []
    merged_split_ids: list[str] = []

    for result in results:
        if (result.symbol, result.interval, result.model_name, result.forecast_horizon) != key:
            raise ValueError("Cannot merge forecast results with mismatched identity fields.")
        prediction_times.extend(result.prediction_times)
        predicted_values.extend(result.predicted_values)
        actual_values.extend(result.actual_values)
        refs = result.metadata.get("reference_values")
        if not isinstance(refs, list | tuple):
            raise ValueError("Each split result must expose metadata['reference_values'] as a sequence.")
        reference_values.extend(float(x) for x in refs)
        merged_split_ids.append(str(result.metadata.get("split_id", "")))

    if len(reference_values) != len(predicted_values):
        raise ValueError("Merged reference_values length must match predictions.")

    return ForecastResult(
        symbol=base.symbol,
        interval=base.interval,
        model_name=base.model_name,
        prediction_times=tuple(prediction_times),
        predicted_values=tuple(predicted_values),
        actual_values=tuple(actual_values),
        forecast_horizon=base.forecast_horizon,
        metadata={
            "merged_split_ids": merged_split_ids,
            "reference_values": reference_values,
        },
    )


def load_experiment_config(path: Path) -> dict[str, Any]:
    """Load and minimally validate experiment JSON."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigurationError("Experiment config must be a JSON object.")
    required = (
        "symbol",
        "interval",
        "model_name",
        "start_time",
        "end_time",
        "window_size",
        "forecast_horizon",
    )
    missing = [key for key in required if key not in raw]
    if missing:
        raise ConfigurationError(f"Experiment config missing required keys: {', '.join(missing)}.")
    return raw


def build_forecast_request(raw: dict[str, Any]) -> ForecastRequest:
    """Build a ForecastRequest from config dict."""
    model_parameters = raw.get("model_parameters")
    if model_parameters is not None and not isinstance(model_parameters, dict):
        raise ConfigurationError("`model_parameters` must be a JSON object when provided.")
    return ForecastRequest(
        symbol=str(raw["symbol"]),
        interval=str(raw["interval"]),
        target_field=str(raw.get("target_field", "close")),
        window_size=int(raw["window_size"]),
        forecast_horizon=int(raw["forecast_horizon"]),
        start_time=parse_iso_datetime(str(raw["start_time"])),
        end_time=parse_iso_datetime(str(raw["end_time"])),
        model_name=str(raw["model_name"]),
        model_parameters=dict(model_parameters or {}),
    )


def run_from_config(
    raw: dict[str, Any],
    *,
    repository: TimescaleMarketDataRepository | None = None,
    progress_callback: Any | None = None,
) -> dict[str, Any]:
    """Execute one experiment; return a JSON-serializable summary dict."""
    request = build_forecast_request(raw)
    validation_size = int(raw.get("validation_size", 1))
    step = raw.get("step_size")
    step_size = None if step is None else int(step)
    required_features = tuple(
        str(name).strip() for name in (raw.get("required_features") or []) if str(name).strip()
    )
    artifacts_dir = Path(raw.get("artifacts_dir", "experiments/results"))
    _emit_progress(
        f"Starting {request.model_name} experiment for {request.symbol} {request.interval}.",
        progress_callback,
    )

    if raw.get("init_schema"):
        _emit_progress("Initializing schema for the requested logical symbol.", progress_callback)
        repo = initialize_database([request.symbol])
    else:
        if repository is None:
            _emit_progress("Creating repository from database settings.", progress_callback)
            db = DatabaseSettings.from_env()
            repo = TimescaleMarketDataRepository(db.connection_string, schema_name=db.schema_name)
        else:
            _emit_progress("Using injected repository instance.", progress_callback)
            repo = repository

    loader = PredictionDatasetLoader(
        market_data_repository=repo,
        feature_window_reader=repo,
        progress_callback=progress_callback,
    )
    store = LocalArtifactStore(artifacts_dir)
    runner = WalkForwardExperimentRunner(
        dataset_loader=loader,
        artifact_store=store,
        progress_callback=progress_callback,
    )
    summary = runner.run(
        request,
        validation_size=validation_size,
        step_size=step_size,
        required_features=required_features,
    )
    _emit_progress(f"Experiment finished. Run id: {summary.run_id}.", progress_callback)

    out: dict[str, Any] = {
        "run_id": summary.run_id,
        "aggregate": {
            "split_id": summary.aggregate_report.split_id,
            "rmse": summary.aggregate_report.rmse,
            "mape": summary.aggregate_report.mape,
            "direction_accuracy": summary.aggregate_report.direction_accuracy,
            "fit_duration_seconds": summary.aggregate_report.fit_duration_seconds,
            "predict_duration_seconds": summary.aggregate_report.predict_duration_seconds,
            "artifact_paths": list(summary.aggregate_report.artifact_paths),
        },
        "splits": [
            {
                "split_id": report.split_id,
                "rmse": report.rmse,
                "mape": report.mape,
                "direction_accuracy": report.direction_accuracy,
                "artifact_paths": list(report.artifact_paths),
            }
            for report in summary.evaluation_reports
        ],
    }

    backtest_raw = raw.get("backtest")
    if isinstance(backtest_raw, dict) and backtest_raw.get("enabled"):
        _emit_progress("Starting backtest over merged split predictions.", progress_callback)
        merged = merge_forecast_results(summary.split_results)
        buy_threshold = float(backtest_raw.get("buy_threshold", 0.0))
        starting_cash = float(backtest_raw.get("starting_cash", 10_000.0))
        policy = ThresholdSignalPolicy(buy_threshold=buy_threshold)
        bt_runner = BacktraderBacktestRunner(market_data_repository=repo)
        report = bt_runner.run_from_forecast_result(
            symbol=request.symbol,
            interval=request.interval,
            start_time=request.start_time,
            end_time=request.end_time,
            forecast_result=merged,
            starting_cash=starting_cash,
            signal_policy=policy,
        )
        out["backtest"] = {
            "trade_count": report.trade_count,
            "profit_factor": report.profit_factor,
            "max_drawdown": report.max_drawdown,
            "sharpe_ratio": report.sharpe_ratio,
            "sortino_ratio": report.sortino_ratio,
            "cumulative_return": report.cumulative_return,
            "buy_and_hold_return": report.buy_and_hold_return,
            "notes": list(report.notes),
        }
        _emit_progress("Backtest finished.", progress_callback)

    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a DB-backed walk-forward forecasting experiment from a JSON config.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to experiment JSON (see experiments/configs/).",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Optional .env path forwarded to settings loaders.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress logs and only print the final JSON summary.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not args.config.is_file():
        raise SystemExit(f"Config file not found: {args.config}")

    progress_callback = build_progress_logger(enabled=not args.quiet)
    try:
        DatabaseSettings.from_env(env_file=args.env_file)
        _emit_progress(f"Loaded experiment config from {args.config}.", progress_callback)
        raw = load_experiment_config(args.config)
        summary = run_from_config(raw, progress_callback=progress_callback)
    except Exception as exc:
        _emit_progress(f"Experiment failed: {exc}", progress_callback)
        raise
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
