"""Typed runtime configuration for exchange connectivity."""

from __future__ import annotations

import os
from dataclasses import dataclass

from capm.core.errors import ConfigurationError

DEMO_SPOT_REST_BASE_URL = "https://demo-api.binance.com"
LIVE_SPOT_REST_BASE_URL = "https://api.binance.com"
SUPPORTED_BINANCE_MODES = {"demo", "live"}


@dataclass(frozen=True, slots=True)
class BinanceSettings:
    """Runtime settings for Binance spot connectivity."""

    mode: str = "demo"
    spot_rest_base_url: str = DEMO_SPOT_REST_BASE_URL
    request_timeout_seconds: float = 10.0
    retry_attempts: int = 3
    retry_backoff_seconds: float = 0.5
    max_klines_per_request: int = 1000
    trust_env: bool = False

    def __post_init__(self) -> None:
        """Validate the settings payload."""
        if self.mode not in SUPPORTED_BINANCE_MODES:
            raise ConfigurationError(
                f"Unsupported Binance mode {self.mode!r}. "
                f"Expected one of {sorted(SUPPORTED_BINANCE_MODES)}."
            )
        if not self.spot_rest_base_url:
            raise ConfigurationError("Binance spot REST base URL cannot be empty.")
        if self.request_timeout_seconds <= 0:
            raise ConfigurationError("Request timeout must be greater than zero.")
        if self.retry_attempts < 1:
            raise ConfigurationError("Retry attempts must be at least one.")
        if self.retry_backoff_seconds < 0:
            raise ConfigurationError("Retry backoff cannot be negative.")
        if not 1 <= self.max_klines_per_request <= 1000:
            raise ConfigurationError("Binance supports 1-1000 klines per request.")

    @classmethod
    def from_env(cls, *, mode: str | None = None) -> "BinanceSettings":
        """Build settings from environment variables."""
        resolved_mode = (mode or os.getenv("CAPM_BINANCE_MODE", "demo")).strip().lower()
        default_base_url = (
            DEMO_SPOT_REST_BASE_URL
            if resolved_mode == "demo"
            else LIVE_SPOT_REST_BASE_URL
        )
        base_url = os.getenv("CAPM_BINANCE_SPOT_REST_BASE_URL", default_base_url).strip()
        timeout = float(os.getenv("CAPM_BINANCE_TIMEOUT_SECONDS", "10"))
        retry_attempts = int(os.getenv("CAPM_BINANCE_RETRY_ATTEMPTS", "3"))
        retry_backoff = float(os.getenv("CAPM_BINANCE_RETRY_BACKOFF_SECONDS", "0.5"))
        trust_env = os.getenv("CAPM_BINANCE_TRUST_ENV", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        return cls(
            mode=resolved_mode,
            spot_rest_base_url=base_url,
            request_timeout_seconds=timeout,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff,
            trust_env=trust_env,
        )
