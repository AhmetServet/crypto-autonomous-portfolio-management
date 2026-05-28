"""Adapters that shape canonical datasets for prediction model families."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from capm.domains.features import FeatureRow
from capm.domains.market_data import OHLCV
from capm.domains.prediction import (
    DatasetAdaptationError,
    ForecastDataset,
    PreparedPredictionStep,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
    TabularPredictionInput,
    TabularTrainingInput,
)


def _to_float(value: Decimal | float | int) -> float:
    return float(value)


def _extract_target_value(row: OHLCV | FeatureRow, target_field: str) -> float:
    candle = row if isinstance(row, OHLCV) else row.candle
    try:
        raw_value = getattr(candle, target_field)
    except AttributeError as exc:
        raise DatasetAdaptationError(f"Unsupported target field {target_field!r}.") from exc
    return _to_float(raw_value)


@dataclass(frozen=True, slots=True)
class StatisticalDatasetAdapter:
    """Shapes candle-backed datasets into univariate model inputs."""

    def prepare_step(self, dataset: ForecastDataset, reference_index: int) -> PreparedPredictionStep:
        if not all(isinstance(row, OHLCV) for row in dataset.rows):
            raise DatasetAdaptationError("Statistical models require OHLCV rows.")
        if reference_index < dataset.window_size:
            raise DatasetAdaptationError("Reference index does not have enough training history.")
        target_index = reference_index + dataset.forecast_horizon
        if target_index >= len(dataset.rows):
            raise DatasetAdaptationError("Reference index exceeds the available forecast horizon.")

        training_rows = dataset.rows[reference_index - dataset.window_size : reference_index]
        reference_row = dataset.rows[reference_index]
        target_row = dataset.rows[target_index]
        training_input = StatisticalTrainingInput(
            timestamps=tuple(row.open_time for row in training_rows),
            target_values=tuple(_extract_target_value(row, dataset.target_field) for row in training_rows),
            interval=dataset.interval,
        )
        prediction_input = StatisticalPredictionInput(
            reference_time=reference_row.open_time,
            prediction_time=target_row.open_time,
            reference_value=_extract_target_value(reference_row, dataset.target_field),
            forecast_horizon=dataset.forecast_horizon,
            interval=dataset.interval,
        )
        return PreparedPredictionStep(
            reference_index=reference_index,
            reference_time=reference_row.open_time,
            prediction_time=target_row.open_time,
            reference_value=prediction_input.reference_value,
            actual_value=_extract_target_value(target_row, dataset.target_field),
            training_input=training_input,
            prediction_input=prediction_input,
        )


def infer_feature_names(rows: tuple[FeatureRow, ...]) -> tuple[str, ...]:
    """Infer a stable feature set from ready rows when one is not declared."""
    ready_rows = [row for row in rows if row.is_feature_ready]
    if not ready_rows:
        raise DatasetAdaptationError("No ready feature rows were available for ML training.")

    common_features = {
        feature_name
        for feature_name, value in ready_rows[0].indicator_values.items()
        if value is not None
    }
    for row in ready_rows[1:]:
        common_features &= {
            feature_name
            for feature_name, value in row.indicator_values.items()
            if value is not None
        }
    if not common_features:
        raise DatasetAdaptationError("Could not infer a complete shared feature set from the dataset.")
    return tuple(sorted(common_features))


@dataclass(frozen=True, slots=True)
class TabularDatasetAdapter:
    """Shapes feature-row datasets into tabular training and prediction inputs."""

    def prepare_step(self, dataset: ForecastDataset, reference_index: int) -> PreparedPredictionStep:
        if not all(isinstance(row, FeatureRow) for row in dataset.rows):
            raise DatasetAdaptationError("Tabular models require feature rows.")
        if reference_index < dataset.window_size:
            raise DatasetAdaptationError("Reference index does not have enough training history.")
        target_index = reference_index + dataset.forecast_horizon
        if target_index >= len(dataset.rows):
            raise DatasetAdaptationError("Reference index exceeds the available forecast horizon.")

        rows = tuple(dataset.rows)
        feature_names = dataset.feature_names or infer_feature_names(rows)
        training_rows = rows[reference_index - dataset.window_size : reference_index]
        reference_row = rows[reference_index]
        target_row = rows[target_index]

        feature_matrix: list[tuple[float, ...]] = []
        target_values: list[float] = []
        timestamps: list[object] = []
        for offset, row in enumerate(training_rows):
            if not row.is_feature_ready:
                raise DatasetAdaptationError("Tabular adapters reject incomplete feature windows.")
            feature_vector = []
            for feature_name in feature_names:
                value = row.indicator_values.get(feature_name)
                if value is None:
                    raise DatasetAdaptationError(
                        f"Feature {feature_name!r} is missing at {row.open_time.isoformat()}."
                    )
                feature_vector.append(_to_float(value))
            feature_matrix.append(tuple(feature_vector))
            timestamps.append(row.open_time)
            aligned_target_row = rows[(reference_index - dataset.window_size) + offset + dataset.forecast_horizon]
            target_values.append(_extract_target_value(aligned_target_row, dataset.target_field))

        if not reference_row.is_feature_ready:
            raise DatasetAdaptationError("The prediction row is not feature-ready.")
        prediction_feature_vector: list[float] = []
        for feature_name in feature_names:
            value = reference_row.indicator_values.get(feature_name)
            if value is None:
                raise DatasetAdaptationError(
                    f"Feature {feature_name!r} is missing at {reference_row.open_time.isoformat()}."
                )
            prediction_feature_vector.append(_to_float(value))

        training_input = TabularTrainingInput(
            timestamps=tuple(timestamps),
            feature_names=feature_names,
            feature_matrix=tuple(feature_matrix),
            target_values=tuple(target_values),
        )
        prediction_input = TabularPredictionInput(
            reference_time=reference_row.open_time,
            prediction_time=target_row.open_time,
            reference_value=_extract_target_value(reference_row, dataset.target_field),
            feature_names=feature_names,
            feature_vector=tuple(prediction_feature_vector),
            forecast_horizon=dataset.forecast_horizon,
        )
        return PreparedPredictionStep(
            reference_index=reference_index,
            reference_time=reference_row.open_time,
            prediction_time=target_row.open_time,
            reference_value=prediction_input.reference_value,
            actual_value=_extract_target_value(target_row, dataset.target_field),
            training_input=training_input,
            prediction_input=prediction_input,
        )
