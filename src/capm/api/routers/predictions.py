"""Prediction runtime and journal routes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from capm.main import build_repository, parse_datetime
from capm.services.prediction_journal import PredictionJournalService
from capm.services.prediction_runtime import PredictionRuntimeService

from ..schemas import JournalSummaryRequest, PredictRequest, SettlePredictionsRequest
from ..shared import datetime_now_minus_interval

router = APIRouter()


@router.post("/api/predict")
def predict(request: PredictRequest) -> object:
    repository = build_repository()
    runtime = PredictionRuntimeService(repository)
    prediction = runtime.predict(
        artifact_path=request.model_artifact,
        symbol=request.symbol,
        interval=request.interval,
        reference_time=parse_datetime(request.at) if request.at else None,
    )
    payload = prediction.to_dict()
    if request.journal:
        journal_entry = PredictionJournalService(
            journal_repository=repository,
            market_data_repository=repository,
        ).journal_prediction(prediction)
        payload["journal_id"] = journal_entry.id
    return jsonable_encoder({"status": "ok", "prediction": payload})


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
