from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from psycopg import Connection
from psycopg_pool import ConnectionPool

from api.config import DATABASE_URL

# Opened by the app lifespan (or the scripts and tests that need it), not at import time
pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False)


def get_db() -> Iterator[Connection]:
    """Borrow a connection for one request; it is rolled back on errors and returned afterwards."""
    with pool.connection() as connection:
        yield connection


DbDep = Annotated[Connection, Depends(get_db)]


def init_db() -> None:
    with pool.connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                disabled BOOLEAN NOT NULL DEFAULT FALSE,
                role TEXT NOT NULL DEFAULT 'driver' CHECK (role IN ('admin', 'driver')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Usernames are unique regardless of case
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_idx ON users (lower(username))"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rides (
                id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                pickup_location TEXT NOT NULL,
                dropoff_location TEXT NOT NULL,
                pickup_time TIMESTAMP NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                available BOOLEAN NOT NULL DEFAULT TRUE,
                created_by INTEGER NOT NULL REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
