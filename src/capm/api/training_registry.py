"""Model artifact discovery and dashboard-managed training jobs."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
import signal
import subprocess
import sys
import threading
from typing import Any
from uuid import uuid4

from capm.main import parse_datetime

MODEL_RESULTS_DIR = Path("experiments/results")
TRAINING_CONFIGS_DIR = Path("experiments/configs")
TRAINING_JOBS_DIR = MODEL_RESULTS_DIR / "dashboard_jobs"
MODEL_REGISTRY_STATE_PATH = MODEL_RESULTS_DIR / "model_registry.json"
TRAINING_JOBS: dict[str, dict[str, Any]] = {}
TRAINING_JOBS_LOCK = threading.RLock()
TRAINING_PROCESSES: dict[str, subprocess.Popen[str]] = {}


def read_model_registry_state() -> dict[str, Any]:
    """Load the persisted registry state, tolerating missing or invalid files."""
    if not MODEL_REGISTRY_STATE_PATH.exists():
        return {"artifacts": {}}
    try:
        payload = json.loads(MODEL_REGISTRY_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"artifacts": {}}
    if not isinstance(payload, dict):
        return {"artifacts": {}}
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        payload["artifacts"] = {}
    return payload


def write_model_registry_state(payload: dict[str, Any]) -> None:
    """Persist the registry state file."""
    MODEL_REGISTRY_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_REGISTRY_STATE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def model_type_from_name(model_name: str | None) -> str:
    """Map a model name to the coarse dashboard model family."""
    normalized = (model_name or "").lower()
    if normalized in {"xgboost", "lightgbm"}:
        return "tabular"
    if normalized in {"lstm", "gru"}:
        return "deep_learning"
    if normalized in {"arima", "prophet"}:
        return "statistical"
    return "unknown"


def load_summary_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    """Extract metrics regardless of trainer output format."""
    metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
    if not metrics:
        metrics = summary.get("aggregate_metrics") if isinstance(summary.get("aggregate_metrics"), dict) else {}
    aggregate = summary.get("aggregate") if isinstance(summary.get("aggregate"), dict) else {}
    return {
        "direction_accuracy": metrics.get("direction_accuracy", aggregate.get("direction_accuracy")),
        "mape": metrics.get("mape", aggregate.get("mape")),
        "rmse": metrics.get("rmse", aggregate.get("rmse")),
    }


def artifact_is_stale(value: object, *, max_age_days: int) -> bool:
    """Determine whether a trained-through timestamp is stale."""
    if not value:
        return True
    try:
        trained_at = parse_datetime(str(value))
    except ValueError:
        return True
    return (datetime.now(UTC) - trained_at).total_seconds() > max_age_days * 86_400


def discover_model_artifacts(
    *,
    symbol: str | None = None,
    interval: str | None = None,
    results_dir: Path | None = None,
    limit: int = 100,
) -> dict[str, object]:
    """Return trained model artifacts from local experiment results."""
    results_dir = results_dir or MODEL_RESULTS_DIR
    registry_state = read_model_registry_state()
    registry_artifacts = registry_state.get("artifacts") if isinstance(registry_state.get("artifacts"), dict) else {}
    artifacts: list[dict[str, object]] = []
    if not results_dir.exists():
        return {"status": "ok", "results_dir": str(results_dir), "artifacts": [], "latest_by_model": []}

    normalized_symbol = symbol.strip().upper() if symbol else None
    normalized_interval = interval.strip() if interval else None
    for summary_path in sorted(results_dir.glob("*/summary.json"), reverse=True):
        try:
            summary = json.loads(summary_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        request = summary.get("request") if isinstance(summary.get("request"), dict) else {}
        metrics = load_summary_metrics(summary)
        backtest = summary.get("backtest") if isinstance(summary.get("backtest"), dict) else {}

        artifact_path = Path(str(summary.get("model_artifact_path") or summary_path.parent / "model.pkl"))
        artifact_kind = "production"
        if not artifact_path.is_file():
            walk_forward_artifact_path = summary_path.parent / "trained_models.pkl"
            if not walk_forward_artifact_path.is_file():
                continue
            artifact_path = walk_forward_artifact_path
            artifact_kind = "walk_forward"
        if not artifact_path.is_file():
            continue

        artifact_key = str(artifact_path)
        artifact_state = registry_artifacts.get(artifact_key) if isinstance(registry_artifacts, dict) else None
        if not isinstance(artifact_state, dict):
            artifact_state = {}
        artifact_symbol = str(summary.get("symbol") or request.get("symbol") or "").upper()
        artifact_interval = str(summary.get("interval") or request.get("interval") or "")
        if normalized_symbol and artifact_symbol != normalized_symbol:
            continue
        if normalized_interval and artifact_interval != normalized_interval:
            continue

        stat = artifact_path.stat()
        trained_through = summary.get("end_time") or request.get("end_time")
        artifacts.append(
            {
                "run_id": summary.get("run_id") or summary_path.parent.name,
                "symbol": artifact_symbol,
                "interval": artifact_interval,
                "model_name": summary.get("model_name") or request.get("model_name"),
                "model_type": model_type_from_name(str(summary.get("model_name") or request.get("model_name") or "")),
                "artifact_kind": artifact_kind,
                "artifact_path": artifact_key,
                "summary_path": str(summary_path),
                "trained_through": trained_through,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
                "direction_accuracy": metrics.get("direction_accuracy"),
                "mape": metrics.get("mape"),
                "rmse": metrics.get("rmse"),
                "cumulative_return": backtest.get("cumulative_return"),
                "trade_count": backtest.get("trade_count"),
                "active": bool(artifact_state.get("active", True)),
                "archived": bool(artifact_state.get("archived", False)),
                "notes": artifact_state.get("notes"),
                "stale": artifact_is_stale(trained_through, max_age_days=3),
            }
        )

    artifacts.sort(key=lambda item: str(item["modified_at"]), reverse=True)
    latest_by_model: dict[str, dict[str, object]] = {}
    for artifact in artifacts:
        if artifact.get("archived") or not artifact.get("active"):
            continue
        model_name = str(artifact.get("model_name") or artifact["run_id"])
        latest_by_model.setdefault(model_name, artifact)
    return {
        "status": "ok",
        "results_dir": str(results_dir),
        "artifacts": artifacts[:limit],
        "latest_by_model": list(latest_by_model.values()),
    }


def training_type_from_config(path: Path, payload: dict[str, Any]) -> str:
    """Infer the trainer family from a config payload."""
    name = path.name.lower()
    model_name = str(payload.get("model_name") or "").lower()
    models = payload.get("models")
    if "deep" in name or model_name in {"lstm", "gru"}:
        return "deep_learning"
    if "walk_forward" in name or model_name in {"arima", "prophet"}:
        return "statistical"
    if isinstance(models, list):
        model_names = {str(item.get("model_name", "")).lower() for item in models if isinstance(item, dict)}
        if model_names & {"lstm", "gru"}:
            return "deep_learning"
        if model_names & {"arima", "prophet"}:
            return "statistical"
    return "tabular"


def training_command(training_type: str, config_path: Path) -> list[str]:
    """Build the subprocess command for a training job."""
    module_by_type = {
        "tabular": "capm.experiments.train_production",
        "deep_learning": "capm.experiments.train_deep_learning",
        "statistical": "capm.experiments.walk_forward",
    }
    module = module_by_type.get(training_type)
    if module is None:
        raise ValueError("Training type must be tabular, deep_learning, or statistical.")
    return [sys.executable, "-m", module, "--config", str(config_path)]


def append_job_log(log_path: Path, message: str) -> None:
    """Append one line to a dashboard job log."""
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message)
        if not message.endswith("\n"):
            handle.write("\n")


def training_job_payload(job: dict[str, Any], *, include_log: bool = False) -> dict[str, Any]:
    """Serialize a dashboard training job."""
    payload = {key: value for key, value in job.items() if key not in {"command"}}
    payload["command"] = list(job["command"])
    if include_log:
        log_path = Path(str(job["log_path"]))
        payload["log"] = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return payload


def run_training_job(job_id: str) -> None:
    """Execute one dashboard training job in a subprocess."""
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS[job_id]
        command = list(job["command"])
        log_path = Path(str(job["log_path"]))
        job["status"] = "running"
        job["started_at"] = datetime.now(UTC).isoformat()
    append_job_log(log_path, f"[dashboard] starting training job {job_id}: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    with TRAINING_JOBS_LOCK:
        TRAINING_PROCESSES[job_id] = process
        TRAINING_JOBS[job_id]["pid"] = process.pid
    try:
        assert process.stdout is not None
        for line in process.stdout:
            append_job_log(log_path, line)
        return_code = process.wait()
    finally:
        with TRAINING_JOBS_LOCK:
            TRAINING_PROCESSES.pop(job_id, None)
    finished_at = datetime.now(UTC).isoformat()
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS[job_id]
        if job.get("status") == "cancel_requested":
            job["status"] = "cancelled"
        else:
            job["status"] = "succeeded" if return_code == 0 else "failed"
        job["return_code"] = return_code
        job["finished_at"] = finished_at
    append_job_log(log_path, f"[dashboard] finished training job {job_id} return_code={return_code}")


def list_training_presets() -> dict[str, object]:
    """Enumerate training presets from the configs directory."""
    presets = []
    for config_path in sorted(TRAINING_CONFIGS_DIR.glob("**/*.json")):
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        presets.append(
            {
                "name": config_path.stem,
                "path": str(config_path),
                "training_type": training_type_from_config(config_path, payload),
                "symbol": payload.get("symbol"),
                "interval": payload.get("interval"),
                "model_name": payload.get("model_name"),
                "description": payload.get("description"),
                "config": payload,
            }
        )
    return {"status": "ok", "presets": presets}


def list_training_jobs() -> dict[str, object]:
    """List in-memory dashboard training jobs."""
    with TRAINING_JOBS_LOCK:
        jobs = [training_job_payload(job) for job in TRAINING_JOBS.values()]
    jobs.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return {"status": "ok", "jobs": jobs}


def get_training_job(job_id: str) -> dict[str, object] | None:
    """Return one in-memory dashboard training job, including logs."""
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.get(job_id)
        if job is None:
            return None
        return {"status": "ok", "job": training_job_payload(job, include_log=True)}


def create_training_job_record(training_type: str, config: dict[str, Any], name: str | None = None) -> dict[str, object]:
    """Create and start a dashboard training job."""
    job_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    job_dir = TRAINING_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    config_path = job_dir / "config.json"
    log_path = job_dir / "training.log"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    command = training_command(training_type, config_path)
    job = {
        "id": job_id,
        "name": name or f"{training_type}-{job_id}",
        "training_type": training_type,
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "finished_at": None,
        "return_code": None,
        "pid": None,
        "config_path": str(config_path),
        "log_path": str(log_path),
        "command": command,
    }
    with TRAINING_JOBS_LOCK:
        TRAINING_JOBS[job_id] = job
    thread = threading.Thread(target=run_training_job, args=(job_id,), daemon=True)
    thread.start()
    return {"status": "ok", "job": training_job_payload(job)}


def cancel_training_job_record(job_id: str) -> dict[str, object] | None:
    """Cancel a running dashboard training job if it exists."""
    with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.get(job_id)
        process = TRAINING_PROCESSES.get(job_id)
        if job is None:
            return None
        if process is None or process.poll() is not None:
            return {"status": "ok", "job": training_job_payload(job)}
        job["status"] = "cancel_requested"
    os.killpg(process.pid, signal.SIGTERM)
    return {"status": "ok", "job": training_job_payload(job)}
