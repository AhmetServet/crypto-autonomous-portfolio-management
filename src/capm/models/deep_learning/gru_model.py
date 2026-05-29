"""GRU forecasting wrapper."""

from __future__ import annotations

from typing import Any

from .base import RecurrentForecastingModel


class GRUForecastingModel(RecurrentForecastingModel):
    """Fits and predicts with a GRU sequence regressor."""

    def __init__(self, model_kwargs: dict[str, Any] | None = None) -> None:
        RecurrentForecastingModel.__init__(
            self,
            cell_type="gru",
            model_kwargs=dict(model_kwargs or {}),
        )
