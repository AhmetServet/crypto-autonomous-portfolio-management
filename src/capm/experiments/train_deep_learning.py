"""CLI: train one production-style LSTM/GRU model and backtest holdout signals."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from capm.core.config import DatabaseSettings
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.training import DeepLearningProductionTrainer, LocalArtifactStore


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_config(path: Path) -> dict[str, Any]:
    """Load a deep-learning training JSON config."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Training config must be a JSON object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    """Build the deep-learning trainer parser."""
    parser = argparse.ArgumentParser(
        description="Train one LSTM/GRU sequence model, save model.pkl, and backtest holdout signals.",
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to deep-learning training JSON config.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logs and print only final JSON.")
    return parser


def _build_progress_logger(enabled: bool):
    started_at = perf_counter()

    def log(message: str) -> None:
        if not enabled:
            return
        elapsed = perf_counter() - started_at
        print(f"[deep-learning +{elapsed:8.2f}s] {message}", file=sys.stderr, flush=True)

    return log


def run_from_config(config: dict[str, Any], *, progress_enabled: bool = True) -> dict[str, Any]:
    """Run one deep-learning training config."""
    progress = _build_progress_logger(progress_enabled)
    progress("loading database settings")
    db = DatabaseSettings.from_env()
    repository = TimescaleMarketDataRepository(db.connection_string, schema_name=db.schema_name)
    trainer = DeepLearningProductionTrainer(
        repository=repository,
        artifact_store=LocalArtifactStore(Path(config.get("artifacts_dir", "experiments/results"))),
    )
    backtest = dict(config.get("backtest", {}))
    result = trainer.train_sequence_model(
        symbol=str(config["symbol"]),
        interval=str(config["interval"]),
        model_name=str(config.get("model_name", "lstm")),
        start_time=parse_iso_datetime(str(config["start_time"])),
        split_time=parse_iso_datetime(str(config["split_time"])),
        end_time=parse_iso_datetime(str(config["end_time"])),
        sequence_length=int(config.get("sequence_length", 240)),
        forecast_horizon=int(config.get("forecast_horizon", 1)),
        target_field=str(config.get("target_field", "close")),
        target_mode=str(config.get("target_mode", "return")),
        scaler_mode=str(config.get("scaler", config.get("scaler_mode", "zscore"))),
        model_parameters=dict(config.get("model_parameters", {})),
        required_features=tuple(str(name) for name in config.get("required_features", ())),
        starting_cash=float(backtest.get("starting_cash", config.get("starting_cash", 10_000.0))),
        buy_threshold=float(backtest.get("buy_threshold", config.get("buy_threshold", 0.001))),
        commission_rate=float(backtest.get("commission_rate", config.get("commission_rate", 0.001))),
        cash_fraction=float(backtest.get("cash_fraction", config.get("cash_fraction", 0.95))),
        progress_callback=progress,
    )
    payload = asdict(result)
    payload["feature_names"] = list(result.feature_names)
    progress("training command complete")
    return payload


def run_many_from_config(config: dict[str, Any], *, progress_enabled: bool = True) -> dict[str, Any]:
    """Run one or more deep-learning model definitions from one config."""
    models = config.get("models")
    if not models:
        return run_from_config(config, progress_enabled=progress_enabled)
    if not isinstance(models, list):
        raise ValueError("models must be a list when provided.")
    results = []
    progress = _build_progress_logger(progress_enabled)
    for index, model in enumerate(models, start=1):
        if not isinstance(model, dict):
            raise ValueError("Each model entry must be a JSON object.")
        merged = dict(config)
        merged.pop("models", None)
        merged["model_name"] = model.get("model_name", model.get("name", merged.get("model_name")))
        merged["model_parameters"] = model.get("model_parameters", model.get("parameters", {}))
        progress(f"starting model {index}/{len(models)}: {merged['model_name']}")
        results.append(run_from_config(merged, progress_enabled=progress_enabled))
    return {
        "ranking_metric": "mape",
        "results": sorted(results, key=lambda item: item["mape"]),
    }


def main() -> None:
    """Run the deep-learning trainer CLI."""
    args = build_parser().parse_args()
    print(json.dumps(run_many_from_config(load_config(args.config), progress_enabled=not args.quiet), indent=2, default=str))


if __name__ == "__main__":
    main()
