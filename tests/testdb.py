"""Point the app at the test database; import this before any `api` module.

The test database is created by `docker compose up -d` (see db/init-test-db.sql).
Tests truncate its tables, so it must never be the development database.
"""
import configparser
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.ini"


def _test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        parser = configparser.ConfigParser()
        parser.read(CONFIG_PATH)
        url = parser.get("database", "test_url", fallback="")
    if not url:
        raise RuntimeError(
            f"Set [database] test_url in {CONFIG_PATH} (see config.ini.example) "
            "or the TEST_DATABASE_URL variable."
        )
    if not url.rsplit("/", 1)[-1].split("?")[0].endswith("_test"):
        raise RuntimeError("The test database name must end in _test.")
    return url


os.environ["DATABASE_URL"] = _test_database_url()
