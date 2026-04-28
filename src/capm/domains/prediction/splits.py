"""Walk-forward split definitions for forecasting experiments."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import SplitValidationError


@dataclass(frozen=True, slots=True)
class WalkForwardSplit:
    """Inclusive-exclusive reference-index range for one validation slice."""

    split_id: str
    reference_start: int
    reference_end: int

    def __post_init__(self) -> None:
        if not self.split_id.strip():
            raise SplitValidationError("`split_id` must not be empty.")
        if self.reference_start < 0:
            raise SplitValidationError("`reference_start` must not be negative.")
        if self.reference_end <= self.reference_start:
            raise SplitValidationError("`reference_end` must be greater than `reference_start`.")

    @property
    def reference_indices(self) -> tuple[int, ...]:
        """Return the reference indices covered by this split."""
        return tuple(range(self.reference_start, self.reference_end))


def build_walk_forward_splits(
    *,
    total_rows: int,
    window_size: int,
    forecast_horizon: int,
    validation_size: int,
    step_size: int | None = None,
) -> tuple[WalkForwardSplit, ...]:
    """Partition valid reference indices into walk-forward validation slices."""
    if total_rows < 1:
        raise SplitValidationError("`total_rows` must be positive.")
    if window_size < 1:
        raise SplitValidationError("`window_size` must be positive.")
    if forecast_horizon < 1:
        raise SplitValidationError("`forecast_horizon` must be positive.")
    if validation_size < 1:
        raise SplitValidationError("`validation_size` must be positive.")

    resolved_step_size = validation_size if step_size is None else step_size
    if resolved_step_size < 1:
        raise SplitValidationError("`step_size` must be positive when provided.")

    first_reference_index = window_size
    last_reference_index = total_rows - forecast_horizon - 1
    if last_reference_index < first_reference_index:
        raise SplitValidationError("The dataset is too short for the requested walk-forward configuration.")

    splits: list[WalkForwardSplit] = []
    split_index = 0
    reference_start = first_reference_index
    while reference_start <= last_reference_index:
        reference_end = min(reference_start + validation_size, last_reference_index + 1)
        splits.append(
            WalkForwardSplit(
                split_id=f"split-{split_index:03d}",
                reference_start=reference_start,
                reference_end=reference_end,
            )
        )
        split_index += 1
        reference_start += resolved_step_size

    return tuple(splits)
