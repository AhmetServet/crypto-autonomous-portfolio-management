"""Typed runtime configuration for exchange and database connectivity."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from capm.core.errors import ConfigurationError

DEMO_SPOT_REST_BASE_URL = "https://demo-api.binance.com"
LIVE_SPOT_REST_BASE_URL = "https://api.binance.com"
SUPPORTED_BINANCE_MODES = {"demo", "live"}
DEFAULT_LLM_BASE_URL = "https://openrouter.ai/api/v1"


def load_environment(env_file: str | None = None) -> None:
    """Load environment variables from a dotenv file if present."""
    load_dotenv(dotenv_path=env_file, override=False)


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
    def from_env(
        cls,
        *,
        mode: str | None = None,
        env_file: str | None = None,
    ) -> "BinanceSettings":
        """Build settings from environment variables."""
        load_environment(env_file)
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


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Runtime settings for database connectivity."""

    connection_string: str
    schema_name: str = "capm"
    ohlcv_write_batch_size: int = 500
    hide_sql_parameters: bool = True

    def __post_init__(self) -> None:
        """Validate the settings payload."""
        if not self.connection_string.strip():
            raise ConfigurationError("Database connection string cannot be empty.")
        if not self.schema_name.strip():
            raise ConfigurationError("Database schema name cannot be empty.")
        if self.ohlcv_write_batch_size < 1:
            raise ConfigurationError("OHLCV write batch size must be at least one.")

    @classmethod
    def from_env(cls, *, env_file: str | None = None) -> "DatabaseSettings":
        """Build database settings from environment variables."""
        load_environment(env_file)
        connection_string = (
            os.getenv("CAPM_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or ""
        ).strip()
        schema_name = os.getenv("CAPM_DATABASE_SCHEMA", "capm").strip()
        ohlcv_write_batch_size = int(os.getenv("CAPM_DATABASE_OHLCV_WRITE_BATCH_SIZE", "500"))
        hide_sql_parameters = os.getenv("CAPM_DATABASE_HIDE_SQL_PARAMETERS", "true").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return cls(
            connection_string=connection_string,
            schema_name=schema_name,
            ohlcv_write_batch_size=ohlcv_write_batch_size,
            hide_sql_parameters=hide_sql_parameters,
        )


@dataclass(frozen=True, slots=True)
class LLMSettings:
    """Runtime settings for an OpenAI-compatible chat-completions API."""

    api_key: str
    model: str
    base_url: str = DEFAULT_LLM_BASE_URL
    request_timeout_seconds: float = 30.0
    retry_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("LLM API key cannot be empty.")
        if not self.model.strip():
            raise ConfigurationError("LLM model cannot be empty.")
        if not self.base_url.strip():
            raise ConfigurationError("LLM base URL cannot be empty.")
        if self.request_timeout_seconds <= 0:
            raise ConfigurationError("LLM request timeout must be greater than zero.")
        if self.retry_attempts < 1:
            raise ConfigurationError("LLM retry attempts must be at least one.")

    @classmethod
    def from_env(cls, *, env_file: str | None = None) -> "LLMSettings":
        """Build provider-compatible LLM settings from environment variables."""
        load_environment(env_file)
        return cls(
            api_key=os.getenv("CAPM_LLM_API_KEY", "").strip(),
            model=os.getenv("CAPM_LLM_MODEL", "").strip(),
            base_url=os.getenv("CAPM_LLM_BASE_URL", DEFAULT_LLM_BASE_URL).strip().rstrip("/"),
            request_timeout_seconds=float(os.getenv("CAPM_LLM_TIMEOUT_SECONDS", "30")),
            retry_attempts=int(os.getenv("CAPM_LLM_RETRY_ATTEMPTS", "3")),
        )
