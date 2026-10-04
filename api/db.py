import sqlite3
from pathlib import Path
from typing import List, Optional

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "relay.db"
CONNECTION = sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    CONNECTION.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            pickup_time DATETIME NOT NULL,
            pickup_location TEXT NOT NULL,
            dropoff_location TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    CONNECTION.commit()


def save_job(session_id: str, pickup_time: str, pickup_location: str, dropoff_location: str, note: str = "") -> int:
    cursor = CONNECTION.execute(
        "INSERT INTO jobs (session_id, pickup_time, pickup_location, dropoff_location, note) VALUES (?, ?, ?, ?, ?)",
        (session_id, pickup_time, pickup_location, dropoff_location, note),
    )
    CONNECTION.commit()

    if cursor.lastrowid is None:
        raise Exception("Failed to retrieve the last inserted row ID.")
    return cursor.lastrowid


def list_jobs(session_id: Optional[str] = None) -> List[dict]:

    statement = "SELECT id, session_id, pickup_time, pickup_location, dropoff_location, note FROM jobs ORDER BY id DESC"
    params = ()
    if session_id is not None:
        statement = "SELECT id, session_id, pickup_time, pickup_location, dropoff_location, note FROM jobs WHERE session_id = ? ORDER BY id DESC"
        params = (session_id,)

    rows = CONNECTION.execute(statement, params).fetchall()
    return [{
        "id": row[0],
        "session_id": row[1],
        "pickup_time": row[2],
        "pickup_location": row[3],
        "dropoff_location": row[4],
        "note": row[5]
    } for row in rows]


def get_job_session_id(job_id: int) -> Optional[str]:
    row = CONNECTION.execute(
        "SELECT session_id FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row[0] if row else None


def delete_job(job_id: int) -> bool:
    cursor = CONNECTION.execute(
        "DELETE FROM jobs WHERE id = ?", (job_id,))
    CONNECTION.commit()
    return cursor.rowcount > 0
