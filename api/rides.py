from datetime import datetime

from psycopg import Connection
from pydantic import BaseModel


class Ride(BaseModel):
    id: int
    pickup_location: str
    dropoff_location: str
    pickup_time: datetime
    notes: str
    created_by: int
    available: bool


def create_ride(
    connection: Connection,
    pickup_location: str,
    dropoff_location: str,
    pickup_time: datetime,
    notes: str,
    created_by: int,
) -> int:
    """Store a ride request, available to drivers, and return its id."""
    row = connection.execute(
        "INSERT INTO rides (pickup_location, dropoff_location, pickup_time, notes, created_by)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (pickup_location, dropoff_location, pickup_time, notes, created_by),
    ).fetchone()
    connection.commit()
    if row is None:
        raise RuntimeError("The ride request was not stored.")
    return row[0]


def list_rides(connection: Connection) -> list[Ride]:
    """All ride requests, earliest pickup first."""
    rows = connection.execute(
        "SELECT id, pickup_location, dropoff_location, pickup_time, notes, created_by, available"
        " FROM rides ORDER BY pickup_time, id"
    ).fetchall()
    return [Ride(**dict(zip(Ride.model_fields, row))) for row in rows]
