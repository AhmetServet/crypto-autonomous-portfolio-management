"""Unit tests for runtime settings."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from capm.core.config.settings import DatabaseSettings


class DatabaseSettingsTests(unittest.TestCase):
    """Exercise dotenv-backed database configuration."""

    def test_database_settings_load_from_dotenv_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "CAPM_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres",
                        "CAPM_DATABASE_SCHEMA=capm",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            original_capm_database_url = os.environ.pop("CAPM_DATABASE_URL", None)
            original_database_url = os.environ.pop("DATABASE_URL", None)
            original_schema_name = os.environ.pop("CAPM_DATABASE_SCHEMA", None)
            try:
                settings = DatabaseSettings.from_env(env_file=str(env_path))
            finally:
                if original_capm_database_url is not None:
                    os.environ["CAPM_DATABASE_URL"] = original_capm_database_url
                if original_database_url is not None:
                    os.environ["DATABASE_URL"] = original_database_url
                if original_schema_name is not None:
                    os.environ["CAPM_DATABASE_SCHEMA"] = original_schema_name

        self.assertEqual(
            settings.connection_string,
            "postgresql://postgres:postgres@localhost:5432/postgres",
        )
        self.assertEqual(settings.schema_name, "capm")


if __name__ == "__main__":
    unittest.main()
