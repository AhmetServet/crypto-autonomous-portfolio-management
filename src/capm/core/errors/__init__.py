"""Shared exception hierarchy for CAPM."""


class CAPMError(Exception):
    """Base exception for all application-specific errors."""


class ConfigurationError(CAPMError):
    """Raised when runtime configuration is invalid."""


class ValidationError(CAPMError):
    """Raised when an input fails domain validation."""


class ExchangeAPIError(CAPMError):
    """Raised when an exchange adapter cannot complete a request."""


class PaginationError(CAPMError):
    """Raised when paginated market data retrieval cannot progress safely."""
