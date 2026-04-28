"""Thin ARIMA forecasting wrapper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import pandas as pd
except ImportError:  # pragma: no cover - optional dependency.
    pd = None

try:
    from statsmodels.tsa.arima.model import ARIMA as StatsmodelsARIMA
except ImportError:  # pragma: no cover - optional dependency.
    StatsmodelsARIMA = None

from capm.domains.prediction import (
    DatasetAdaptationError,
    MissingOptionalDependencyError,
    StatisticalPredictionInput,
    StatisticalTrainingInput,
)
from capm.domains.market_data import interval_to_timedelta


@dataclass(slots=True)
class ARIMAForecastingModel:
    """Fits and predicts with statsmodels ARIMA."""

    order: tuple[int, int, int] = (1, 0, 0)
    trend: str | None = None
    fit_kwargs: dict[str, Any] = field(default_factory=dict)
    _results: Any | None = field(init=False, default=None, repr=False)

    name: str = "arima"
    family: str = "statistical"

    def _build_training_series(self, training_input: StatisticalTrainingInput) -> Any:
        """Build a frequency-aware pandas series for statsmodels."""
        if pd is None:
            raise MissingOptionalDependencyError("ARIMA support requires the optional `pandas` dependency.")

        frequency = pd.tseries.frequencies.to_offset(interval_to_timedelta(training_input.interval))
        try:
            index = pd.DatetimeIndex(training_input.timestamps, freq=frequency)
        except ValueError as exc:
            raise DatasetAdaptationError(
                "ARIMA training timestamps must be contiguous and match the requested interval."
            ) from exc
        return pd.Series(
            training_input.target_values,
            index=index,
            dtype="float64",
        )

    def fit(self, training_input: StatisticalTrainingInput) -> dict[str, Any]:
        """Fit the ARIMA model on one univariate series."""
        if pd is None or StatsmodelsARIMA is None:
            raise MissingOptionalDependencyError(
                "ARIMA support requires the optional `ml` dependencies (`pandas` and `statsmodels`)."
            )
        if not isinstance(training_input, StatisticalTrainingInput):
            raise DatasetAdaptationError("ARIMA expects a statistical training input.")

        series = self._build_training_series(training_input)
        model = StatsmodelsARIMA(series, order=self.order, trend=self.trend)
        self._results = model.fit(**self.fit_kwargs)
        return {
            "order": list(self.order),
            "aic": float(self._results.aic) if getattr(self._results, "aic", None) is not None else None,
            "bic": float(self._results.bic) if getattr(self._results, "bic", None) is not None else None,
        }

    def predict(self, prediction_input: StatisticalPredictionInput) -> tuple[float, dict[str, Any]]:
        """Forecast the configured horizon and return the final step."""
        if self._results is None:
            raise DatasetAdaptationError("The ARIMA model must be fit before prediction.")
        if not isinstance(prediction_input, StatisticalPredictionInput):
            raise DatasetAdaptationError("ARIMA expects a statistical prediction input.")

        forecast = self._results.forecast(steps=prediction_input.forecast_horizon)
        if hasattr(forecast, "iloc"):
            predicted_value = float(forecast.iloc[-1])
        else:
            predicted_value = float(forecast[-1])
        return predicted_value, {
            "prediction_time": prediction_input.prediction_time.isoformat(),
            "forecast_horizon": prediction_input.forecast_horizon,
        }
