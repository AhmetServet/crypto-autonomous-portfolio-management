"""Pure metric helpers for forecast and portfolio evaluation."""

from __future__ import annotations

from math import sqrt

from .entities import EvaluationReport
from .errors import PredictionValidationError


def _validate_aligned_sequences(
    predicted_values: tuple[float, ...],
    actual_values: tuple[float, ...],
) -> None:
    if not predicted_values or not actual_values:
        raise PredictionValidationError("Metric inputs must not be empty.")
    if len(predicted_values) != len(actual_values):
        raise PredictionValidationError("Metric inputs must align by index.")


def rmse(predicted_values: tuple[float, ...], actual_values: tuple[float, ...]) -> float:
    """Return the root mean squared error for aligned forecast values."""
    _validate_aligned_sequences(predicted_values, actual_values)
    squared_error = sum((actual - predicted) ** 2 for predicted, actual in zip(predicted_values, actual_values, strict=True))
    return sqrt(squared_error / len(predicted_values))


def mape(predicted_values: tuple[float, ...], actual_values: tuple[float, ...]) -> float:
    """Return the mean absolute percentage error for aligned forecast values."""
    _validate_aligned_sequences(predicted_values, actual_values)
    if any(actual == 0 for actual in actual_values):
        raise PredictionValidationError("MAPE is undefined when actual values include zero.")
    percentage_error = sum(
        abs((actual - predicted) / actual)
        for predicted, actual in zip(predicted_values, actual_values, strict=True)
    )
    return percentage_error / len(predicted_values)


def direction_accuracy(
    *,
    predicted_values: tuple[float, ...],
    actual_values: tuple[float, ...],
    reference_values: tuple[float, ...],
) -> float:
    """Return the share of predictions with the correct directional move."""
    _validate_aligned_sequences(predicted_values, actual_values)
    if len(reference_values) != len(predicted_values):
        raise PredictionValidationError("`reference_values` must align with prediction values.")

    def _sign(value: float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    hits = 0
    for predicted, actual, reference in zip(predicted_values, actual_values, reference_values, strict=True):
        if _sign(predicted - reference) == _sign(actual - reference):
            hits += 1
    return hits / len(predicted_values)


def aggregate_reports(reports: tuple[EvaluationReport, ...]) -> dict[str, float]:
    """Return arithmetic means for the primary metrics across splits."""
    if not reports:
        raise PredictionValidationError("At least one report is required for aggregation.")
    report_count = len(reports)
    return {
        "rmse": sum(report.rmse for report in reports) / report_count,
        "mape": sum(report.mape for report in reports) / report_count,
        "direction_accuracy": sum(report.direction_accuracy for report in reports) / report_count,
        "fit_duration_seconds": sum(report.fit_duration_seconds for report in reports),
        "predict_duration_seconds": sum(report.predict_duration_seconds for report in reports),
    }
