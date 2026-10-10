import logging
import uvicorn

from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated

from fastapi import (
    Depends,
    Form,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi_csrf_protect.exceptions import CsrfProtectError
from fastapi_csrf_protect.flexible import CsrfProtect

from api.config import (
    ACCESS_TOKEN_EXPIRE_SECONDS,
    AUTH_COOKIE,
    BASE_DIR,
    CSRF_COOKIE_SAMESITE,
    CSRF_SECRET,
    CSRF_TOKEN_KEY,
    FRONTEND_DIR,
    IS_DEVELOPMENT,
    templates,
)
from api.db import init_db
from api.forms import (
    LoginFormData,
    SignupFormData,
    _auth_page,
    template_response_with_csrf,
    validate_form_csrf,
)
from api.auth import (
    Token,
    authenticate_user,
    create_access_token,
    create_user,
    get_current_user,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ride Request Board", lifespan=lifespan)
app.state.development_mode = IS_DEVELOPMENT


@CsrfProtect.load_config
def get_csrf_config():
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
async def revalidate_cached_responses(request: Request, call_next):
    # Without this, browsers heuristically cache static assets and /api responses
    response = await call_next(request)
    if request.url.path.startswith(("/ui/static", "/api/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


class ConnectionManager:
    """Fans the events out to every connected WebSocket client."""

    def __init__(self):
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("Client connected (active: %s)",
                    len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.discard(websocket)
            logger.info(
                "Client disconnected (active: %s)", len(
                    self.active_connections)
            )

    async def broadcast(self, message: str) -> None:
        for websocket in self.active_connections.copy():
            try:
                await websocket.send_text(message)
            except (WebSocketDisconnect, RuntimeError):
                self.disconnect(websocket)


manager = ConnectionManager()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
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
    return await request_validation_exception_handler(request, exc)


@app.get("/", include_in_schema=False)
async def root(request: Request):
    """Landing page for visitors; logged-in users are redirected to /account."""
    try:
        await get_current_user(request.cookies.get(AUTH_COOKIE))
    except HTTPException:
        return templates.TemplateResponse(request, "index.html")
    return RedirectResponse("/account", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/signup", include_in_schema=False)
async def get_signup_page(request: Request, csrf_protect: CsrfProtect = Depends()):
    return _auth_page(request, csrf_protect, "signup.html")


@app.post("/signup", include_in_schema=False)
async def post_signup_page(
    request: Request,
    csrf_protect: Annotated[CsrfProtect, Depends()],
    form: Annotated[SignupFormData, Form()],
):
    await validate_form_csrf(request, csrf_protect)
    if create_user(form.username, form.password) is None:
        return _auth_page(
            request,
            csrf_protect,
            "signup.html",
            error="Username is already taken",
            username=form.username,
            status_code=status.HTTP_409_CONFLICT,
        )
    return RedirectResponse("/login?created=true", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", include_in_schema=False)
async def get_login_page(
    request: Request, csrf_protect: CsrfProtect = Depends(), created: bool = False
):
    try:
        await get_current_user(request.cookies.get(AUTH_COOKIE))
    except HTTPException:
        return _auth_page(request, csrf_protect, "login.html", created=created)
    return RedirectResponse("/account", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/login", include_in_schema=False)
async def post_login_page(
    request: Request,
    csrf_protect: Annotated[CsrfProtect, Depends()],
    form: Annotated[LoginFormData, Form()],
):
    await validate_form_csrf(request, csrf_protect)
    user = authenticate_user(form.username, form.password)
    if not user:
        return _auth_page(
            request,
            csrf_protect,
            "login.html",
            error="Incorrect username or password",
            username=form.username,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS),
    )
    response = RedirectResponse(
        "/account", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        AUTH_COOKIE,
        access_token,
        max_age=ACCESS_TOKEN_EXPIRE_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout", include_in_schema=False)
async def post_logout(request: Request, csrf_protect: CsrfProtect = Depends()):
    await validate_form_csrf(request, csrf_protect)
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(AUTH_COOKIE)
    return response


@app.get("/account", include_in_schema=False)
async def get_account(request: Request, csrf_protect: CsrfProtect = Depends()):
    try:
        user = await get_current_user(request.cookies.get(AUTH_COOKIE))
    except HTTPException:
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return template_response_with_csrf(request, "home.html", {"user": user}, csrf_protect)


@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    user = authenticate_user(form_data.username, form_data.password)
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


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket,) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# Mounted last so it never shadows the API/page routes defined above; serves CSS/JS assets only.
app.mount("/ui/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


def run_server(port: int = 8080) -> None:
    uvicorn.run(
        "api.main:app",
        app_dir=str(BASE_DIR),
        host="0.0.0.0",
        port=port,
        reload=IS_DEVELOPMENT,
        reload_dirs=[str(BASE_DIR)],
    )


if __name__ == "__main__":
    port = 8080
    logger.info(f"Starting server on http://localhost:{port}")
    run_server()
