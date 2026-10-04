import hashlib
import hmac
import secrets
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
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            pickup_time DATETIME NOT NULL,
            pickup_location TEXT NOT NULL,
            dropoff_location TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    CONNECTION.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'driver' CHECK (role IN ('dispatcher', 'driver')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    columns = [row[1] for row in CONNECTION.execute("PRAGMA table_info(users)")]
    if "role" not in columns:
        CONNECTION.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'driver'")
    CONNECTION.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    job_columns = [row[1] for row in CONNECTION.execute("PRAGMA table_info(jobs)")]
    if "user_id" not in job_columns:
        CONNECTION.execute("ALTER TABLE jobs ADD COLUMN user_id INTEGER REFERENCES users(id) ON DELETE SET NULL")
    if "session_id" in job_columns:
        CONNECTION.execute("ALTER TABLE jobs DROP COLUMN session_id")
    CONNECTION.commit()


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1).hex()


def create_user(username: str, password: str, role: str) -> Optional[int]:
    """Create a user; return its id, or None if the username is taken."""
    salt = secrets.token_bytes(16)
    stored = f"{salt.hex()}${_hash_password(password, salt)}"
    try:
        cursor = CONNECTION.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", (username, stored, role))
    except sqlite3.IntegrityError:
        return None
    CONNECTION.commit()
    return cursor.lastrowid


def verify_user(username: str, password: str) -> Optional[int]:
    row = CONNECTION.execute(
        "SELECT id, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    salt_hex, expected = row[1].split("$")
    actual = _hash_password(password, bytes.fromhex(salt_hex))
    return row[0] if hmac.compare_digest(actual, expected) else None


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_auth_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    CONNECTION.execute(
        "INSERT INTO auth_sessions (token_hash, user_id) VALUES (?, ?)", (_token_hash(token), user_id))
    CONNECTION.commit()
    return token


def get_user_by_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    row = CONNECTION.execute(
        "SELECT u.id, u.username, u.role FROM auth_sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (_token_hash(token),)).fetchone()
    return {"id": row[0], "username": row[1], "role": row[2]} if row else None


def delete_auth_session(token: Optional[str]) -> None:
    if token:
        CONNECTION.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
        CONNECTION.commit()


def save_job(user_id: int, pickup_time: str, pickup_location: str, dropoff_location: str, note: str = "") -> int:
    cursor = CONNECTION.execute(
        "INSERT INTO jobs (user_id, pickup_time, pickup_location, dropoff_location, note) VALUES (?, ?, ?, ?, ?)",
        (user_id, pickup_time, pickup_location, dropoff_location, note),
    )
    CONNECTION.commit()

    if cursor.lastrowid is None:
        raise Exception("Failed to retrieve the last inserted row ID.")
    return cursor.lastrowid


def list_jobs() -> List[dict]:
    statement = "SELECT id, user_id, pickup_time, pickup_location, dropoff_location, note FROM jobs ORDER BY id DESC"
    params = ()

    rows = CONNECTION.execute(statement, params).fetchall()
    return [{
        "id": row[0],
        "user_id": row[1],
        "pickup_time": row[2],
        "pickup_location": row[3],
        "dropoff_location": row[4],
        "note": row[5]
    } for row in rows]


def delete_job(job_id: int) -> bool:
    cursor = CONNECTION.execute(
        "DELETE FROM jobs WHERE id = ?", (job_id,))
    CONNECTION.commit()
    return cursor.rowcount > 0
