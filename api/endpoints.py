from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from api.auth import Token, authenticate_user, create_access_token
from api.config import ACCESS_TOKEN_EXPIRE_SECONDS
from api.db import DbDep

api_router = APIRouter(prefix="/api", tags=["health"])
token_router = APIRouter(tags=["auth"])


@api_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@token_router.post("/token")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    connection: DbDep,
) -> Token:
    user = authenticate_user(connection, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
