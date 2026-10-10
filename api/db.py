import sqlite3

from api.config import BASE_DIR

DB_PATH = BASE_DIR / "jobhub.db"
CONNECTION = sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    CONNECTION.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            disabled BOOLEAN NOT NULL DEFAULT FALSE,
            role TEXT NOT NULL DEFAULT 'driver' CHECK (role IN ('admin', 'driver')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    CONNECTION.commit()
