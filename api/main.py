import logging

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_csrf_protect.exceptions import CsrfProtectError
from fastapi_csrf_protect.flexible import CsrfProtect

from api import admin, endpoints, pages, ws
from api.admin import admin_page
from api.auth import (
    get_admin_from_cookie,
    get_user_from_cookie,
    get_user_from_token,
    set_auth_cookie,
)
from api.config import (
    AUTH_COOKIE,
    CSRF_COOKIE_SAMESITE,
    CSRF_SECRET,
    CSRF_TOKEN_KEY,
    FRONTEND_DIR,
)
from api.db import init_db, pool
from api.forms import RIDE_LOCATION_MAX_LENGTH, RIDE_NOTES_MAX_LENGTH, _auth_page


logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    pool.open(wait=True, timeout=10)
    try:
        init_db()
        yield
    finally:
        pool.close()


app = FastAPI(title="Ride Request Board", lifespan=lifespan)


@CsrfProtect.load_config
def get_csrf_config() -> list[tuple[str, str]]:
    return [
        ("secret_key", CSRF_SECRET),
        ("cookie_samesite", CSRF_COOKIE_SAMESITE),
        ("token_key", CSRF_TOKEN_KEY),
    ]


@app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(
    request: Request, exc: CsrfProtectError
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.middleware("http")
async def refresh_auth_cookie(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Set the renewed login token that `get_optional_user_from_cookie` left on the request."""
    response = await call_next(request)
    token = getattr(request.state, "refreshed_auth_token", None)
    if token:
        set_auth_cookie(response, token)
    return response


@app.middleware("http")
async def revalidate_cached_responses(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    # Without this, browsers heuristically cache static assets and /api responses
    response = await call_next(request)
    if request.url.path.startswith(("/ui/static", "/api/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


def _admin_form_error_page(request: Request, body: Mapping) -> Response:
    """Re-render the dashboard for an invalid ride form (blocking, so run it in a thread)."""
    with pool.connection() as connection:
        # The admin check ran before validation, so this only fails if the session just ended
        user = get_user_from_token(connection, request.cookies.get(AUTH_COOKIE))
        admin = get_admin_from_cookie(get_user_from_cookie(user))
        return admin_page(
            request,
            connection,
            CsrfProtect(),
            admin,
            error=(
                "Enter a pickup and drop-off location (up to "
                f"{RIDE_LOCATION_MAX_LENGTH} characters), a valid pickup date and time, "
                f"and notes of up to {RIDE_NOTES_MAX_LENGTH} characters."
            ),
            form={
                "pickup_location": str(body.get("pickup_location", ""))[:RIDE_LOCATION_MAX_LENGTH],
                "dropoff_location": str(body.get("dropoff_location", ""))[:RIDE_LOCATION_MAX_LENGTH],
                "pickup_time": str(body.get("pickup_time", ""))[:32],
                "notes": str(body.get("notes", ""))[:RIDE_NOTES_MAX_LENGTH],
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> Response:
    """Re-render the signup or login form with an error instead of returning raw JSON."""

    body = exc.body if isinstance(exc.body, Mapping) else {}

    if request.method == "POST" and request.url.path == "/login":
        return _auth_page(
            request,
            CsrfProtect(),
            "login.html",
            error="Incorrect username or password",
            username=body.get("username", ""),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if request.method == "POST" and request.url.path == "/signup":
        return _auth_page(
            request,
            CsrfProtect(),
            "signup.html",
            error="Username: 3-32 letters, digits or underscores. Password: 8-128 characters.",
            username=body.get("username", ""),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    if request.method == "POST" and request.url.path == "/admin/rides":
        return await run_in_threadpool(_admin_form_error_page, request, body)
    return await request_validation_exception_handler(request, exc)


app.include_router(pages.router)
app.include_router(admin.router)
app.include_router(endpoints.api_router)
app.include_router(endpoints.token_router)
app.include_router(ws.router)


# Mounted last so it never shadows the API/page routes defined above; serves CSS/JS assets only.
app.mount("/ui/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
