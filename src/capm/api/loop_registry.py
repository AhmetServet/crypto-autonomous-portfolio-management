"""Dashboard-managed live agent loop processes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import os
import signal
import subprocess
import sys
import threading
from typing import Any
from uuid import uuid4

from .schemas import LiveCycleLoopRequest

LOOP_JOBS_DIR = Path("experiments/results/dashboard_loops")
LOOP_JOBS: dict[str, dict[str, Any]] = {}
LOOP_JOBS_LOCK = threading.RLock()
LOOP_PROCESSES: dict[str, subprocess.Popen[str]] = {}


def append_loop_log(log_path: Path, message: str) -> None:
    """Append one line to a dashboard loop log."""
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message)
        if not message.endswith("\n"):
            handle.write("\n")


def loop_command(request: LiveCycleLoopRequest) -> list[str]:
    """Build the CLI command used by a dashboard loop process."""
    command = [
        str(Path(sys.executable).with_name("capm")),
        "agent",
        "run-loop",
        "--interval",
        request.interval,
        "--mode",
        request.mode,
        "--market-data-mode",
        request.market_data_mode,
        "--max-inline-gap-minutes",
        str(request.max_inline_gap_minutes),
        "--max-model-age-days",
        str(request.max_model_age_days),
        "--max-trade-usdt",
        str(request.max_trade_usdt),
        "--max-position-usdt",
        str(request.max_position_usdt),
        "--max-daily-realized-loss-usdt",
        str(request.max_daily_realized_loss_usdt),
        "--max-orders-per-day",
        str(request.max_orders_per_day),
        "--order-cooldown-minutes",
        str(request.order_cooldown_minutes),
        "--max-total-exposure-usdt",
        str(request.max_total_exposure_usdt),
        "--cycle-offset-seconds",
        str(request.cycle_offset_seconds),
        "--stop-after-error-count",
        str(request.stop_after_error_count),
        "--sleep-after-error-seconds",
        str(request.sleep_after_error_seconds),
    ]
    for artifact in request.model_artifacts:
        command.extend(["--model-artifact", artifact])
    if request.allow_large_gap_recovery:
        command.append("--allow-large-gap-recovery")
    if request.allow_stale_models:
        command.append("--allow-stale-models")
    if request.emergency_stop:
        command.append("--emergency-stop")
    if request.max_cycles is not None:
        command.extend(["--max-cycles", str(request.max_cycles)])
    return command


def loop_job_payload(job: dict[str, Any], *, include_log: bool = False) -> dict[str, Any]:
    """Serialize one dashboard loop job."""
    payload = {key: value for key, value in job.items() if key not in {"command"}}
    payload["command"] = list(job["command"])
    if include_log:
        log_path = Path(str(job["log_path"]))
        payload["log"] = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return payload


def run_loop_job(job_id: str) -> None:
    """Execute one dashboard-managed live loop subprocess."""
    with LOOP_JOBS_LOCK:
        job = LOOP_JOBS[job_id]
        command = list(job["command"])
        log_path = Path(str(job["log_path"]))
        job["status"] = "running"
        job["started_at"] = datetime.now(UTC).isoformat()
    append_loop_log(log_path, f"[dashboard] starting live loop {job_id}: {' '.join(command)}")
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
    with LOOP_JOBS_LOCK:
        LOOP_PROCESSES[job_id] = process
        LOOP_JOBS[job_id]["pid"] = process.pid
    return_code = None
    try:
        assert process.stdout is not None
        for line in process.stdout:
            append_loop_log(log_path, line)
        return_code = process.wait()
    finally:
        with LOOP_JOBS_LOCK:
            LOOP_PROCESSES.pop(job_id, None)
    finished_at = datetime.now(UTC).isoformat()
    with LOOP_JOBS_LOCK:
        job = LOOP_JOBS[job_id]
        if job.get("status") == "stop_requested":
            job["status"] = "stopped"
        else:
            job["status"] = "completed" if return_code == 0 else "failed"
        job["return_code"] = return_code
        job["finished_at"] = finished_at
    append_loop_log(log_path, f"[dashboard] finished live loop {job_id} return_code={return_code}")


def list_loop_jobs() -> dict[str, object]:
    """List in-memory dashboard live loops."""
    with LOOP_JOBS_LOCK:
        loops = [loop_job_payload(job) for job in LOOP_JOBS.values()]
    loops.sort(key=lambda item: str(item["created_at"]), reverse=True)
    return {"status": "ok", "loops": loops}


def get_loop_job(job_id: str) -> dict[str, object] | None:
    """Return one dashboard loop job with logs."""
    with LOOP_JOBS_LOCK:
        job = LOOP_JOBS.get(job_id)
        if job is None:
            return None
        return {"status": "ok", "loop": loop_job_payload(job, include_log=True)}


def create_loop_job(request: LiveCycleLoopRequest) -> dict[str, object]:
    """Create and start a dashboard-managed live loop."""
    with LOOP_JOBS_LOCK:
        running = [job for job in LOOP_JOBS.values() if job.get("status") in {"queued", "running"}]
    if running:
        raise ValueError(f"Live loop {running[0]['id']} is already {running[0]['status']}. Stop it before starting another.")

    job_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    job_dir = LOOP_JOBS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    log_path = job_dir / "loop.log"
    command = loop_command(request)
    job = {
        "id": job_id,
        "name": request.name or f"{request.interval}-{request.mode}-loop",
        "status": "queued",
        "created_at": datetime.now(UTC).isoformat(),
        "started_at": None,
        "finished_at": None,
        "return_code": None,
        "pid": None,
        "interval": request.interval,
        "mode": request.mode,
        "market_data_mode": request.market_data_mode,
        "max_cycles": request.max_cycles,
        "cycle_offset_seconds": request.cycle_offset_seconds,
        "log_path": str(log_path),
        "command": command,
    }
    with LOOP_JOBS_LOCK:
        LOOP_JOBS[job_id] = job
    thread = threading.Thread(target=run_loop_job, args=(job_id,), daemon=True)
    thread.start()
    return {"status": "ok", "loop": loop_job_payload(job)}


def stop_loop_job(job_id: str) -> dict[str, object] | None:
    """Stop a running dashboard live loop."""
    with LOOP_JOBS_LOCK:
        job = LOOP_JOBS.get(job_id)
        process = LOOP_PROCESSES.get(job_id)
        if job is None:
            return None
        if process is None or process.poll() is not None:
            return {"status": "ok", "loop": loop_job_payload(job)}
        job["status"] = "stop_requested"
    os.killpg(process.pid, signal.SIGTERM)
    return {"status": "ok", "loop": loop_job_payload(job)}
