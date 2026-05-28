"""Walk-forward experiment orchestration for prediction models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from capm.core.contracts import ArtifactStorePort, DatasetLoaderPort
from capm.domains.prediction import (
    EvaluationReport,
    ExperimentRunSummary,
    ForecastDataset,
    ForecastRequest,
    ForecastResult,
    PredictionValidationError,
    aggregate_reports,
    build_walk_forward_splits,
    direction_accuracy,
    mape,
    rmse,
)
from capm.models import create_model, get_model_family

from .adapters import StatisticalDatasetAdapter, TabularDatasetAdapter


def _serialize_forecast_request(request: ForecastRequest) -> dict[str, Any]:
    payload = asdict(request)
    if request.start_time is not None:
        payload["start_time"] = request.start_time.isoformat()
    if request.end_time is not None:
        payload["end_time"] = request.end_time.isoformat()
    return payload


def _serialize_forecast_result(result: ForecastResult) -> dict[str, Any]:
    return {
        "symbol": result.symbol,
        "interval": result.interval,
        "model_name": result.model_name,
        "prediction_times": [timestamp.isoformat() for timestamp in result.prediction_times],
        "predicted_values": list(result.predicted_values),
        "actual_values": list(result.actual_values),
        "forecast_horizon": result.forecast_horizon,
        "metadata": dict(result.metadata),
    }


def _serialize_evaluation_report(report: EvaluationReport) -> dict[str, Any]:
    payload = asdict(report)
    payload["artifact_paths"] = list(report.artifact_paths)
    return payload


def _build_trained_model_payload(
    *,
    split_id: str,
    model_name: str,
    latest_reference_index: int | None,
    latest_reference_time: datetime | None,
    latest_prediction_time: datetime | None,
    model: Any,
) -> dict[str, Any]:
    """Build one persisted trained-model entry for a split."""
    return {
        "split_id": split_id,
        "model_name": model_name,
        "latest_reference_index": latest_reference_index,
        "latest_reference_time": latest_reference_time.isoformat() if latest_reference_time is not None else None,
        "latest_prediction_time": latest_prediction_time.isoformat() if latest_prediction_time is not None else None,
        "model": model,
    }


@dataclass(slots=True)
class WalkForwardExperimentRunner:
    """Runs walk-forward forecasting experiments over DB-backed datasets."""

    dataset_loader: DatasetLoaderPort
    artifact_store: ArtifactStorePort | None = None
    progress_callback: Callable[[str], None] | None = None

    def _emit_progress(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)

    def run(
        self,
        request: ForecastRequest,
        *,
        validation_size: int = 1,
        step_size: int | None = None,
        required_features: tuple[str, ...] = (),
    ) -> ExperimentRunSummary:
        """Run one walk-forward experiment and return split plus aggregate reports."""
        model_family = get_model_family(request.model_name)
        resolved_required_features = required_features or tuple(
            feature_name
            for feature_name in request.model_parameters.get("feature_names", ())
            if isinstance(feature_name, str) and feature_name.strip()
        )

        if model_family == "statistical":
            dataset = self.dataset_loader.load_statistical_dataset(request)
            adapter = StatisticalDatasetAdapter()
        else:
            dataset = self.dataset_loader.load_tabular_dataset(
                request,
                required_features=resolved_required_features,
            )
            adapter = TabularDatasetAdapter()

        self._emit_progress(
            f"Prepared {model_family} dataset with {dataset.row_count} rows for model `{request.model_name}`."
        )
        splits = build_walk_forward_splits(
            total_rows=dataset.row_count,
            window_size=dataset.window_size,
            forecast_horizon=dataset.forecast_horizon,
            validation_size=validation_size,
            step_size=step_size,
        )
        self._emit_progress(f"Built {len(splits)} walk-forward splits.")
        run_id = self._build_run_id(request)
        request_artifact_path: str | None = None

        if self.artifact_store is not None:
            request_artifact_path = self.artifact_store.write_json(
                run_id=run_id,
                relative_path="request.json",
                payload=_serialize_forecast_request(request),
            )

        split_results: list[ForecastResult] = []
        reports: list[EvaluationReport] = []
        trained_models: list[dict[str, Any]] = []
        total_splits = len(splits)
        for split_index, split in enumerate(splits, start=1):
            self._emit_progress(
                f"Running split {split_index}/{total_splits} "
                f"({split.split_id}, {len(split.reference_indices)} validation steps)."
            )
            forecast_result, evaluation_report, trained_model_payload = self._run_split(
                dataset=dataset,
                request=request,
                adapter=adapter,
                split_id=split.split_id,
                reference_indices=split.reference_indices,
            )
            split_results.append(forecast_result)
            reports.append(evaluation_report)
            trained_models.append(trained_model_payload)
            self._emit_progress(
                f"Finished {split.split_id}: rmse={evaluation_report.rmse:.6f}, "
                f"mape={evaluation_report.mape:.6f}, "
                f"direction_accuracy={evaluation_report.direction_accuracy:.4f}."
            )

        split_artifact_paths: tuple[str, ...] = ()
        if self.artifact_store is not None:
            split_predictions_path = self.artifact_store.write_json(
                run_id=run_id,
                relative_path="split_predictions.json",
                payload=[_serialize_forecast_result(result) for result in split_results],
            )
            split_reports_path = self.artifact_store.write_json(
                run_id=run_id,
                relative_path="split_reports.json",
                payload=[_serialize_evaluation_report(report) for report in reports],
            )
            trained_models_path = self.artifact_store.write_pickle(
                run_id=run_id,
                relative_path="trained_models.pkl",
                payload={
                    "saved_model_scope": "latest_model_per_split",
                    "models": trained_models,
                },
            )
            split_artifact_paths = (
                split_predictions_path,
                split_reports_path,
                trained_models_path,
            )
            reports = [
                EvaluationReport(
                    symbol=report.symbol,
                    interval=report.interval,
                    model_name=report.model_name,
                    split_id=report.split_id,
                    rmse=report.rmse,
                    mape=report.mape,
                    direction_accuracy=report.direction_accuracy,
                    fit_duration_seconds=report.fit_duration_seconds,
                    predict_duration_seconds=report.predict_duration_seconds,
                    artifact_paths=split_artifact_paths,
                )
                for report in reports
            ]

        aggregate_metrics = aggregate_reports(tuple(reports))
        summary_payload = {
            "request": _serialize_forecast_request(request),
            "splits": [_serialize_evaluation_report(report) for report in reports],
            "aggregate_metrics": aggregate_metrics,
        }
        summary_artifact_paths: tuple[str, ...] = ()
        if self.artifact_store is not None:
            summary_path = self.artifact_store.write_json(
                run_id=run_id,
                relative_path="summary.json",
                payload=summary_payload,
            )
            summary_artifact_paths = tuple(
                path
                for path in (
                    request_artifact_path,
                    *split_artifact_paths,
                    summary_path,
                )
                if path is not None
            )
            self._emit_progress(
                "Persisted consolidated run artifacts: request.json, split_predictions.json, "
                "split_reports.json, trained_models.pkl, summary.json."
            )

        aggregate_report = EvaluationReport(
            symbol=request.symbol,
            interval=request.interval,
            model_name=request.model_name,
            split_id="aggregate",
            rmse=aggregate_metrics["rmse"],
            mape=aggregate_metrics["mape"],
            direction_accuracy=aggregate_metrics["direction_accuracy"],
            fit_duration_seconds=aggregate_metrics["fit_duration_seconds"],
            predict_duration_seconds=aggregate_metrics["predict_duration_seconds"],
            artifact_paths=summary_artifact_paths,
        )
        self._emit_progress(
            f"Completed run {run_id}: aggregate rmse={aggregate_report.rmse:.6f}, "
            f"mape={aggregate_report.mape:.6f}, "
            f"direction_accuracy={aggregate_report.direction_accuracy:.4f}."
        )
        return ExperimentRunSummary(
            run_id=run_id,
            request=request,
            split_results=tuple(split_results),
            evaluation_reports=tuple(reports),
            aggregate_report=aggregate_report,
        )

    def _run_split(
        self,
        *,
        dataset: ForecastDataset,
        request: ForecastRequest,
        adapter: StatisticalDatasetAdapter | TabularDatasetAdapter,
        split_id: str,
        reference_indices: tuple[int, ...],
    ) -> tuple[ForecastResult, EvaluationReport, dict[str, Any]]:
        predicted_values: list[float] = []
        actual_values: list[float] = []
        reference_values: list[float] = []
        prediction_times: list[datetime] = []
        fit_duration_seconds = 0.0
        predict_duration_seconds = 0.0
        fit_details: list[dict[str, Any]] = []
        predict_details: list[dict[str, Any]] = []
        latest_model: Any | None = None
        latest_reference_index: int | None = None
        latest_reference_time: datetime | None = None
        latest_prediction_time: datetime | None = None

        for reference_index in reference_indices:
            prepared_step = adapter.prepare_step(dataset, reference_index)
            model = create_model(
                request.model_name,
                parameters=self._model_parameters_without_feature_names(request.model_parameters),
            )

            fit_started = perf_counter()
            fit_detail = model.fit(prepared_step.training_input)
            fit_duration_seconds += perf_counter() - fit_started

            predict_started = perf_counter()
            predicted_value, predict_detail = model.predict(prepared_step.prediction_input)
            predict_duration_seconds += perf_counter() - predict_started

            predicted_values.append(predicted_value)
            actual_values.append(prepared_step.actual_value)
            reference_values.append(prepared_step.reference_value)
            prediction_times.append(prepared_step.prediction_time)
            fit_details.append(fit_detail)
            predict_details.append(predict_detail)
            latest_model = model
            latest_reference_index = prepared_step.reference_index
            latest_reference_time = prepared_step.reference_time
            latest_prediction_time = prepared_step.prediction_time

        forecast_result = ForecastResult(
            symbol=request.symbol,
            interval=request.interval,
            model_name=request.model_name,
            prediction_times=tuple(prediction_times),
            predicted_values=tuple(predicted_values),
            actual_values=tuple(actual_values),
            forecast_horizon=request.forecast_horizon,
            metadata={
                "split_id": split_id,
                "reference_values": list(reference_values),
                "fit_details": fit_details,
                "predict_details": predict_details,
            },
        )

        evaluation_report = EvaluationReport(
            symbol=request.symbol,
            interval=request.interval,
            model_name=request.model_name,
            split_id=split_id,
            rmse=rmse(forecast_result.predicted_values, forecast_result.actual_values),
            mape=mape(forecast_result.predicted_values, forecast_result.actual_values),
            direction_accuracy=direction_accuracy(
                predicted_values=forecast_result.predicted_values,
                actual_values=forecast_result.actual_values,
                reference_values=tuple(reference_values),
            ),
            fit_duration_seconds=fit_duration_seconds,
            predict_duration_seconds=predict_duration_seconds,
            artifact_paths=(),
        )

        return (
            forecast_result,
            evaluation_report,
            _build_trained_model_payload(
                split_id=split_id,
                model_name=request.model_name,
                latest_reference_index=latest_reference_index,
                latest_reference_time=latest_reference_time,
                latest_prediction_time=latest_prediction_time,
                model=latest_model,
            ),
        )

    @staticmethod
    def _model_parameters_without_feature_names(model_parameters: dict[str, Any]) -> dict[str, Any]:
        parameters = dict(model_parameters)
        parameters.pop("feature_names", None)
        return parameters

    @staticmethod
    def _build_run_id(request: ForecastRequest) -> str:
        if request.start_time is None or request.end_time is None:
            raise PredictionValidationError("Experiments require `start_time` and `end_time`.")
        started_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return (
            f"{started_at}_{request.symbol.lower()}_{request.interval}_"
            f"{request.model_name}_{request.forecast_horizon}h"
        )
