"""CLI: train one production-ready tabular model and backtest its holdout signals."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

from capm.core.config import DatabaseSettings
from capm.infra.database.timescale import TimescaleMarketDataRepository
from capm.services.training import LocalArtifactStore, ProductionModelTrainer


def parse_iso_datetime(value: str) -> datetime:
    """Parse an ISO-8601 datetime and normalize it to UTC."""
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def load_config(path: Path) -> dict[str, Any]:
    """Load a production-training JSON config."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Training config must be a JSON object.")
    return payload


def build_parser() -> argparse.ArgumentParser:
    """Build the production trainer parser."""
    parser = argparse.ArgumentParser(
        description="Train one production tabular model, save model.pkl, and backtest holdout signals.",
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to production training JSON config.")
    return parser


def run_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Run production training from a parsed JSON config."""
    db = DatabaseSettings.from_env()
    repository = TimescaleMarketDataRepository(db.connection_string, schema_name=db.schema_name)
    trainer = ProductionModelTrainer(
        repository=repository,
        artifact_store=LocalArtifactStore(Path(config.get("artifacts_dir", "experiments/results"))),
    )
    result = trainer.train_tabular_model(
        symbol=str(config["symbol"]),
        interval=str(config["interval"]),
        model_name=str(config.get("model_name", "xgboost")),
        start_time=parse_iso_datetime(str(config["start_time"])),
        split_time=parse_iso_datetime(str(config["split_time"])),
        end_time=parse_iso_datetime(str(config["end_time"])),
        forecast_horizon=int(config.get("forecast_horizon", 1)),
        target_field=str(config.get("target_field", "close")),
        target_mode=str(config.get("target_mode", "return")),
        calibration_time=(
            parse_iso_datetime(str(config["calibration_time"]))
            if config.get("calibration_time") is not None
            else None
        ),
        model_parameters=dict(config.get("model_parameters", {})),
        required_features=tuple(str(name) for name in config.get("required_features", ())),
        starting_cash=float(config.get("starting_cash", 10_000.0)),
        buy_threshold=float(config.get("buy_threshold", 0.001)),
        commission_rate=float(config.get("commission_rate", 0.001)),
        cash_fraction=float(config.get("cash_fraction", 0.95)),
    )
    payload = asdict(result)
    payload["feature_names"] = list(result.feature_names)
    return payload


def run_many_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Run one or more model definitions from a shared production-training config."""
    models = config.get("models")
    if not models:
        return run_from_config(config)
    if not isinstance(models, list):
        raise ValueError("`models` must be a list when provided.")

    results = []
    for model in models:
        if not isinstance(model, dict):
            raise ValueError("Each model entry must be a JSON object.")
        merged = dict(config)
        merged.pop("models", None)
        merged["model_name"] = model.get("model_name", model.get("name", merged.get("model_name")))
        merged["model_parameters"] = model.get("model_parameters", model.get("parameters", {}))
        results.append(run_from_config(merged))
    ranked = sorted(
        results,
        key=lambda item: item["backtest"]["cumulative_return"],
        reverse=True,
    )
    return {
        "ranking_metric": "backtest.cumulative_return",
        "results": ranked,
    }


def main() -> None:
    """Run the production trainer CLI."""
    args = build_parser().parse_args()
    summary = run_many_from_config(load_config(args.config))
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
