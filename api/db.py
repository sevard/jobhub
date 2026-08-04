import sqlite3
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "relay.db"
CONNECTION = sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db() -> None:
    CONNECTION.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    CONNECTION.commit()


def save_message(session_id: str, message: str) -> int:
    cursor = CONNECTION.execute(
        "INSERT INTO messages (session_id, content) VALUES (?, ?)",
        (session_id, message),
    )
    CONNECTION.commit()
    return cursor.lastrowid


def list_messages() -> List[dict]:
    rows = CONNECTION.execute(
        "SELECT id, session_id, content FROM messages ORDER BY id DESC"
    ).fetchall()
    return [{"id": row[0], "session_id": row[1], "content": row[2]} for row in rows]


def get_message_session_id(message_id: int) -> str:
    row = CONNECTION.execute("SELECT session_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    return row[0] if row else None


def delete_message(message_id: int) -> bool:
    cursor = CONNECTION.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    CONNECTION.commit()
    return cursor.rowcount > 0
