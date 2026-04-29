"""Unit tests for the schema bootstrap helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from capm.core.config.settings import DatabaseSettings


class InitDbTests(unittest.TestCase):
    """Exercise schema-oriented bootstrap configuration."""

    def test_database_settings_include_schema_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "CAPM_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres",
                        "CAPM_DATABASE_SCHEMA=capm",
                        "CAPM_DATABASE_OHLCV_WRITE_BATCH_SIZE=300",
                        "CAPM_DATABASE_HIDE_SQL_PARAMETERS=true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            original_capm_database_url = os.environ.pop("CAPM_DATABASE_URL", None)
            original_database_url = os.environ.pop("DATABASE_URL", None)
            original_schema_name = os.environ.pop("CAPM_DATABASE_SCHEMA", None)
            original_ohlcv_write_batch_size = os.environ.pop("CAPM_DATABASE_OHLCV_WRITE_BATCH_SIZE", None)
            original_hide_sql_parameters = os.environ.pop("CAPM_DATABASE_HIDE_SQL_PARAMETERS", None)
            try:
                settings = DatabaseSettings.from_env(env_file=str(env_path))
            finally:
                if original_capm_database_url is not None:
                    os.environ["CAPM_DATABASE_URL"] = original_capm_database_url
                if original_database_url is not None:
                    os.environ["DATABASE_URL"] = original_database_url
                if original_schema_name is not None:
                    os.environ["CAPM_DATABASE_SCHEMA"] = original_schema_name
                if original_ohlcv_write_batch_size is not None:
                    os.environ["CAPM_DATABASE_OHLCV_WRITE_BATCH_SIZE"] = original_ohlcv_write_batch_size
                if original_hide_sql_parameters is not None:
                    os.environ["CAPM_DATABASE_HIDE_SQL_PARAMETERS"] = original_hide_sql_parameters

        self.assertEqual(settings.schema_name, "capm")
        self.assertEqual(settings.ohlcv_write_batch_size, 300)
        self.assertTrue(settings.hide_sql_parameters)


if __name__ == "__main__":
    unittest.main()
