"""Model artifact and training job routes."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from ..schemas import ModelArtifactStateRequest, TrainingJobRequest
from ..training_registry import (
    cancel_training_job_record,
    create_training_job_record,
    discover_model_artifacts,
    get_training_job,
    list_training_jobs,
    list_training_presets,
    read_model_registry_state,
    write_model_registry_state,
)

router = APIRouter()


@router.get("/api/model-artifacts")
def model_artifacts(
    symbol: str | None = Query(default=None, min_length=1),
    interval: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
) -> object:
    return jsonable_encoder(discover_model_artifacts(symbol=symbol, interval=interval, limit=limit))


@router.post("/api/model-artifacts/state")
def update_model_artifact_state(request: ModelArtifactStateRequest) -> object:
    state = read_model_registry_state()
    artifacts = state.setdefault("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}
        state["artifacts"] = artifacts
    item = artifacts.setdefault(request.artifact_path, {})
    if not isinstance(item, dict):
        item = {}
        artifacts[request.artifact_path] = item
    if request.active is not None:
        item["active"] = request.active
    if request.archived is not None:
        item["archived"] = request.archived
    if request.notes is not None:
        item["notes"] = request.notes
    item["updated_at"] = datetime.now(UTC).isoformat()
    write_model_registry_state(state)
    return jsonable_encoder({"status": "ok", "artifact_path": request.artifact_path, "state": item})


@router.get("/api/training/presets")
def training_presets() -> object:
    return jsonable_encoder(list_training_presets())


@router.get("/api/training/jobs")
def training_jobs() -> object:
    return jsonable_encoder(list_training_jobs())


@router.get("/api/training/jobs/{job_id}")
def training_job(job_id: str) -> object:
    payload = get_training_job(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} was not found.")
    return jsonable_encoder(payload)


@router.post("/api/training/jobs")
def create_training_job(request: TrainingJobRequest) -> object:
    if not request.config:
        raise HTTPException(status_code=400, detail="Training config is required.")
    return jsonable_encoder(create_training_job_record(request.training_type, request.config, request.name))


@router.post("/api/training/jobs/{job_id}/cancel")
def cancel_training_job(job_id: str) -> object:
    payload = cancel_training_job_record(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Training job {job_id} was not found.")
    return jsonable_encoder(payload)
