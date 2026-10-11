import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional, get_args

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from psycopg import Connection, errors
from pwdlib import PasswordHash
from pydantic import BaseModel

from api.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    ACCESS_TOKEN_REFRESH_SECONDS,
    ALGORITHM,
    AUTH_COOKIE,
    SECRET_KEY,
    SESSION_MAX_SECONDS,
)
from api.db import DbDep


password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


Role = Literal["admin", "driver"]


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    username: str
    password: str | None = None
    disabled: bool = False
    role: Role = "driver"


class UserInDB(User):
    id: int
    hashed_password: str


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Create a password hash."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return password_hash.hash(password)


def _get_user_by_username(connection: Connection, username: str) -> UserInDB | None:
    row = connection.execute(
        "SELECT username, password_hash, disabled, role, id FROM users"
        " WHERE lower(username) = lower(%s)",
        (username,),
    ).fetchone()
    if row:
        return UserInDB(
            username=row[0],
            hashed_password=row[1],
            disabled=bool(row[2]),
            role=row[3],
            id=row[4],
        )
    return None


def authenticate_user(connection: Connection, username: str, password: str):
    user = _get_user_by_username(connection, username)
    if not user:
        # This ensures the endpoint takes roughly the same
        # amount of time to respond whether the username is
        # valid or not, preventing timing attacks that could
        # be used to enumerate existing usernames.
        verify_password(password, DUMMY_HASH)
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _session_expiry(started_at: float, now: float) -> int:
    """When a login cookie token issued at `now` expires: 24 hours, but never past the 7-day cap."""
    return int(min(now + ACCESS_TOKEN_EXPIRE_SECONDS, started_at + SESSION_MAX_SECONDS))


def create_session_token(username: str, started_at: float | None = None) -> str:
    """A login cookie token.

    `started_at` is when the user really logged in. It is stored in the
    `auth_time` claim and carried over every renewal, so renewals stop
    `SESSION_MAX_SECONDS` after the login.
    """
    now = time.time()
    started_at = int(now if started_at is None else started_at)
    expires_at = _session_expiry(started_at, now)
    return create_access_token(
        {"sub": username, "auth_time": started_at},
        timedelta(seconds=expires_at - now),
    )


def decode_access_token(token: str | None) -> dict | None:
    """The claims of a valid, unexpired access token, or None."""
    if not token:
        return None
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None


def get_user_from_payload(connection: Connection, payload: dict | None) -> UserInDB | None:
    """The user named by the token claims, read from the database, or None."""
    if payload is None:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return _get_user_by_username(connection, username)


def get_user_from_token(connection: Connection, token: str | None) -> UserInDB | None:
    """Return the user a valid access token belongs to, or None."""
    return get_user_from_payload(connection, decode_access_token(token))


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        httponly=True,
        samesite="lax",
    )


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], connection: DbDep
):
    user = get_user_from_token(connection, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def get_current_admin(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def get_current_driver(
    current_user: Annotated[UserInDB, Depends(get_current_user)],
):
    if current_user.role != "driver":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Driver access required")
    return current_user


def get_optional_user_from_cookie(
    request: Request, connection: DbDep
) -> UserInDB | None:
    """The user behind the auth cookie, or None when logged out (for HTML pages).

    A token that is about to expire is replaced: the new token is parked on the
    request, and the `refresh_auth_cookie` middleware sets it on the response.
    Active users therefore stay logged in, while idle users still expire, and no
    login lasts longer than `SESSION_MAX_SECONDS` from the real login.
    """
    payload = decode_access_token(request.cookies.get(AUTH_COOKIE))
    user = get_user_from_payload(connection, payload)
    if user is not None and payload is not None:
        now = time.time()
        expires_at = payload.get("exp")
        started_at = payload.get("auth_time")
        # Tokens without auth_time are never renewed; they just run out
        if (
            expires_at is not None
            and isinstance(started_at, int)
            and expires_at - now < ACCESS_TOKEN_REFRESH_SECONDS
            and _session_expiry(started_at, now) > expires_at
        ):
            request.state.refreshed_auth_token = create_session_token(
                user.username, started_at
            )
    return user


OptionalUserDep = Annotated[UserInDB | None, Depends(get_optional_user_from_cookie)]


def get_user_from_cookie(user: OptionalUserDep) -> UserInDB:
    """The logged-in user for HTML pages; logged-out visitors are redirected to /login."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"}
        )
    return user


UserDep = Annotated[UserInDB, Depends(get_user_from_cookie)]


def get_admin_from_cookie(user: UserDep) -> UserInDB:
    """The admin behind the auth cookie, for HTML pages.

    Logged-out visitors are redirected to /login; other users get a 403.
    """
    return get_current_admin(user)


AdminDep = Annotated[UserInDB, Depends(get_admin_from_cookie)]


def create_user(
    connection: Connection, username: str, password: str, role: Role = "driver"
) -> Optional[int]:
    """Create a user; return its id, or None if the username is taken.

    Only trusted code (the create_admin script) may pass a role; the signup
    route must never take it from the request.
    """
    if role not in get_args(Role):
        raise ValueError(f"Unknown role: {role!r}")
    try:
        row = connection.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) RETURNING id",
            (username, get_password_hash(password), role),
        ).fetchone()
    except errors.UniqueViolation:
        connection.rollback()
        return None
    connection.commit()
    return row[0] if row else None


def set_user_role(connection: Connection, username: str, role: Role) -> bool:
    """Change a user's role; return False if the user does not exist."""
    cursor = connection.execute(
        "UPDATE users SET role = %s WHERE lower(username) = lower(%s)", (role, username))
    connection.commit()
    return cursor.rowcount == 1
