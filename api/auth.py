import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pydantic import BaseModel

from api.config import ALGORITHM, SECRET_KEY
from api.db import CONNECTION


password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummypassword")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class Token(BaseModel):
    access_token: str
    token_type: str


class User(BaseModel):
    username: str
    password: str | None = None
    disabled: bool = False


class UserInDB(User):
    hashed_password: str


def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Create a password hash."""
    if not password:
        raise ValueError("Password cannot be empty.")
    return password_hash.hash(password)


def _get_user_by_username(username: str):
    row = CONNECTION.execute(
        "SELECT username, password_hash, disabled FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row:
        return UserInDB(
            username=row[0], hashed_password=row[1], disabled=bool(row[2]))
    return None


def authenticate_user(username: str,  password: str):
    user = _get_user_by_username(username)
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


def get_user_from_token(token: str | None) -> UserInDB | None:
    """Return the user a valid access token belongs to, or None."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None
    username = payload.get("sub")
    if not username:
        return None
    return _get_user_by_username(username=username)


async def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]):
    user = get_user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


def create_user(username: str, password: str) -> Optional[int]:
    """Create a user; return its id, or None if the username is taken."""
    try:
        cursor = CONNECTION.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, get_password_hash(password)),
        )
    except sqlite3.IntegrityError:
        return None
    CONNECTION.commit()
    return cursor.lastrowid
