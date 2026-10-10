from datetime import datetime

from pydantic import BaseModel

from api.db import CONNECTION


class Ride(BaseModel):
    id: int
    pickup_location: str
    dropoff_location: str
    pickup_time: datetime
    notes: str
    created_by: int
    available: bool


def create_ride(
    pickup_location: str,
    dropoff_location: str,
    pickup_time: datetime,
    notes: str,
    created_by: int,
) -> int:
    """Store a ride request, available to drivers, and return its id."""
    cursor = CONNECTION.execute(
        "INSERT INTO rides (pickup_location, dropoff_location, pickup_time, notes, created_by)"
        " VALUES (?, ?, ?, ?, ?)",
        (pickup_location, dropoff_location, pickup_time.isoformat(), notes, created_by),
    )
    CONNECTION.commit()
    if cursor.lastrowid is None:
        raise RuntimeError("The ride request was not stored.")
    return cursor.lastrowid


def list_rides() -> list[Ride]:
    """All ride requests, earliest pickup first."""
    rows = CONNECTION.execute(
        "SELECT id, pickup_location, dropoff_location, pickup_time, notes, created_by, available"
        " FROM rides ORDER BY pickup_time, id"
    ).fetchall()
    return [Ride(**dict(zip(Ride.model_fields, row))) for row in rows]
