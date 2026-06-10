"""Prediction runtime and journal routes."""

from __future__ import annotations

import json
import subprocess
import sys

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from capm.main import build_repository, parse_datetime
from capm.services.prediction_journal import PredictionJournalService

from ..schemas import JournalSummaryRequest, PredictBatchRequest, PredictRequest, SettlePredictionsRequest
from ..shared import datetime_now_minus_interval

router = APIRouter()


def _prediction_payload(prediction) -> dict[str, object]:
    """Return dashboard-friendly prediction details."""
    payload = prediction.to_dict() if hasattr(prediction, "to_dict") else dict(prediction)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    sequence_length = metadata.get("sequence_length")
    payload["feature_window"] = {
        "reference_time": payload["reference_time"],
        "prediction_time": payload["prediction_time"],
        "forecast_horizon": payload["forecast_horizon"],
        "feature_names": payload["feature_names"],
        "window_size": sequence_length if sequence_length is not None else 1,
    }
    return payload


def _run_prediction_worker(request: PredictRequest, artifact_path: str) -> dict[str, object]:
    """Run one prediction in an isolated process so native ML crashes do not kill the API."""
    command = [
        sys.executable,
        "-m",
        "capm.predict_worker",
        "--model-artifact",
        artifact_path,
        "--symbol",
        request.symbol,
        "--interval",
        request.interval,
    ]
    if request.at:
        command.extend(["--at", request.at])
    if not request.journal:
        command.append("--no-journal")
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"worker exited with code {completed.returncode}"
        raise RuntimeError(detail)
    output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise RuntimeError("prediction worker returned no output")
    try:
        payload = json.loads(output_lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"prediction worker returned invalid JSON: {output_lines[-1]}") from exc
    prediction = payload.get("prediction")
    if not isinstance(prediction, dict):
        raise RuntimeError("prediction worker response did not include a prediction payload")
    prediction_payload = _prediction_payload(prediction)
    if "journal_id" in payload:
        prediction_payload["journal_id"] = payload["journal_id"]
    return prediction_payload


@router.post("/api/predict")
def predict(request: PredictRequest) -> object:
    try:
        payload = _run_prediction_worker(request, request.model_artifact)
    except Exception as exc:  # noqa: BLE001 - API should return worker failure details.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return jsonable_encoder({"status": "ok", "prediction": payload})


@router.post("/api/predict/batch")
def predict_batch(request: PredictBatchRequest) -> object:
    reference_time = parse_datetime(request.at) if request.at else None
    results = []
    success_count = 0
    error_count = 0
    for artifact_path in request.model_artifacts:
        try:
            payload = _run_prediction_worker(
                PredictRequest(
                    model_artifact=artifact_path,
                    symbol=request.symbol,
                    interval=request.interval,
                    at=request.at,
                    journal=request.journal,
                ),
                artifact_path,
            )
            results.append({"status": "ok", "artifact_path": artifact_path, "prediction": payload})
            success_count += 1
        except Exception as exc:  # noqa: BLE001 - API returns per-artifact prediction failures.
            results.append(
                {
                    "status": "error",
                    "artifact_path": artifact_path,
                    "error_type": type(exc).__name__,
                    "reason": str(exc),
                }
            )
            error_count += 1
    return jsonable_encoder(
        {
            "status": "ok",
            "symbol": request.symbol,
            "interval": request.interval,
            "reference_time": reference_time,
            "success_count": success_count,
            "error_count": error_count,
            "results": results,
        }
    )


@router.post("/api/predictions/settle")
def settle_predictions(request: SettlePredictionsRequest) -> object:
    repository = build_repository()
    until = parse_datetime(request.until) if request.until else datetime_now_minus_interval(request.interval)
    result = PredictionJournalService(
        journal_repository=repository,
        market_data_repository=repository,
    ).settle_predictions(
        symbol=request.symbol,
        interval=request.interval,
        until=until,
        limit=request.limit,
    )
    return jsonable_encoder({"status": "ok", **result})


@router.post("/api/prediction-journal/summary")
def prediction_journal_summary(request: JournalSummaryRequest) -> object:
    repository = build_repository()
    summary = PredictionJournalService(
        journal_repository=repository,
        market_data_repository=repository,
    ).summarize(
        symbol=request.symbol,
        interval=request.interval,
        start_time=parse_datetime(request.start),
        end_time=parse_datetime(request.end),
        model_name=request.model_name,
    )
    return jsonable_encoder({"status": "ok", "summary": summary.to_dict()})
