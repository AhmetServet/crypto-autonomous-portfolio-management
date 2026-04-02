"""Feature and indicator-specific exceptions."""

from capm.core.errors import ValidationError


class FeatureValidationError(ValidationError):
    """Raised when feature-domain inputs are invalid."""


class IndicatorConfigurationError(FeatureValidationError):
    """Raised when an indicator spec contains invalid parameters."""


class FeatureGapError(FeatureValidationError):
    """Raised when a candle series contains a gap or misalignment."""


class IncompleteWindowError(FeatureValidationError):
    """Raised when a requested feature window cannot be assembled."""
