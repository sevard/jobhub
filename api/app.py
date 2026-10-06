import os
import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError

from pydantic import BaseModel, Field, ValidationError
# from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "ui"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")

AUTH_COOKIE = "auth_token"

from api.db import (
    create_auth_session,
    create_user,
    delete_auth_session,
    delete_job,
    get_user_by_token,
    init_db,
    list_jobs,
    save_job,
    verify_user,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

is_development = os.getenv("APP_ENV", "production").lower() == "development"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Ride Request Board", lifespan=lifespan)
app.state.development_mode = is_development


@app.middleware("http")
async def revalidate_cached_responses(request: Request, call_next):
    # Without this, browsers heuristically cache static assets and /api responses
    response = await call_next(request)
    if request.url.path.startswith(("/ui/static", "/api/")):
        response.headers["Cache-Control"] = "no-cache"
    return response


class JobPayload(BaseModel):
    pickup_time: datetime
    pickup_location: str
    dropoff_location: str
    note: str = ""


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)


class SignupPayload(Credentials):
    role: Literal["dispatcher", "driver"]


class ConnectionManager:
    """Fans job events out to every connected WebSocket client."""

    def __init__(self):
        # TODO: change to some other in memory like redis
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info("Client connected (active: %s)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.discard(websocket)
            logger.info(
                "Client disconnected (active: %s)", len(self.active_connections)
            )

    async def broadcast(self, message: str) -> None:
        for websocket in self.active_connections.copy():
            try:
                await websocket.send_text(message)
            except (WebSocketDisconnect, RuntimeError):
                self.disconnect(websocket)


manager = ConnectionManager()


@CsrfProtect.load_config
def get_csrf_config():
    return [
        ("secret_key", os.getenv("CSRF_SECRET", secrets.token_hex(32))),
        ("cookie_samesite", "lax"),
        ("token_key", "csrf_token"),
    ]


@app.exception_handler(CsrfProtectError)
async def csrf_protect_exception_handler(
    request: Request, exc: CsrfProtectError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


def _template_response_with_csrf(
    request: Request,
    template_name: str,
    context: dict,
    csrf_protect: CsrfProtect,
    status_code: int = 200,
):
    csrf_token, signed_token = csrf_protect.generate_csrf_tokens()
    response = templates.TemplateResponse(
        request,
        template_name,
        {**context, "csrf_token": csrf_token},
        status_code=status_code,
    )
    csrf_protect.set_csrf_cookie(signed_token, response)
    return response


async def validate_form_csrf(request: Request, csrf_protect: CsrfProtect) -> dict:
    """Validate the csrf_token hidden field of a server-rendered form and return the fields."""
    form = dict(await request.form())
    # Per-request instance; the library declares _token_location as a ClassVar,
    # so setattr (instance attribute) avoids the type error without changing the class
    setattr(csrf_protect, "_token_location", "body")
    await csrf_protect.validate_csrf(request)
    return form


def current_user(request: Request):
    return get_user_by_token(request.cookies.get(AUTH_COOKIE))


def _start_login(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=create_auth_session(user_id),
        httponly=True,
        samesite="lax",
    )


def _account_page(
    request: Request,
    csrf_protect: CsrfProtect,
    mode: str = "login",
    error: str = "",
    status_code: int = 200,
):
    return _template_response_with_csrf(
        request,
        "account.html",
        {"mode": "signup" if mode == "signup" else "login", "error": error},
        csrf_protect,
        status_code,
    )


def _role_account_page(
    request: Request, role: str, csrf_protect: CsrfProtect
):
    user = current_user(request)
    if not user:
        return RedirectResponse("/account", status_code=303)
    if user["role"] != role:
        return RedirectResponse(f"/account/{user['role']}", status_code=303)
    return _template_response_with_csrf(
        request, f"account_{role}.html", {"user": user}, csrf_protect
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/info")
async def root():
    return {
        "service": "relay-backend",
        "status": "running",
        "websocket_endpoints": ["/ws"],
        "development_mode": app.state.development_mode,
        "note": "WebSocket relay that broadcasts job events to all connected clients.",
    }


@app.get("/", include_in_schema=False)
async def ui_landing(request: Request):
    if current_user(request):
        return RedirectResponse("/account/home", status_code=303)
    return templates.TemplateResponse(request, "account_landing.html")


@app.get("/account", include_in_schema=False)
async def ui_account(
    request: Request, mode: str = "login", csrf_protect: CsrfProtect = Depends()
):
    if current_user(request):
        return RedirectResponse("/account/home", status_code=303)
    return _account_page(request, csrf_protect, mode)


@app.get("/account/home", include_in_schema=False)
async def ui_account_home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/account", status_code=303)
    return RedirectResponse(f"/account/{user['role']}", status_code=303)


@app.post("/account/login", include_in_schema=False)
async def ui_login(request: Request, csrf_protect: CsrfProtect = Depends()):
    form = await validate_form_csrf(request, csrf_protect)
    try:
        creds = Credentials.model_validate(form)
    except ValidationError:
        return _account_page(
            request, csrf_protect, "login",
            "Enter a valid username and a password of at least 8 characters.", 422)

    user_id = verify_user(creds.username, creds.password)
    if user_id is None:
        return _account_page(
            request, csrf_protect, "login", "Invalid username or password", 401)

    response = RedirectResponse("/account/home", status_code=303)
    _start_login(response, user_id)
    return response


@app.post("/account/signup", include_in_schema=False)
async def ui_signup(request: Request, csrf_protect: CsrfProtect = Depends()):
    form = await validate_form_csrf(request, csrf_protect)
    try:
        payload = SignupPayload.model_validate(form)
    except ValidationError:
        return _account_page(
            request, csrf_protect, "signup",
            "Username: 3-32 letters, digits or underscores. Password: 8-128 characters.", 422)
    user_id = create_user(payload.username, payload.password, payload.role)
    if user_id is None:
        return _account_page(
            request, csrf_protect, "signup", "Username is already taken", 409)
    response = RedirectResponse("/account/home", status_code=303)
    _start_login(response, user_id)
    return response


@app.post("/account/logout", include_in_schema=False)
async def ui_logout(request: Request, csrf_protect: CsrfProtect = Depends()):
    await validate_form_csrf(request, csrf_protect)
    delete_auth_session(request.cookies.get(AUTH_COOKIE))
    response = RedirectResponse("/account", status_code=303)
    response.delete_cookie(AUTH_COOKIE)
    return response


@app.get("/account/dispatcher", include_in_schema=False)
async def ui_account_dispatcher(
    request: Request, csrf_protect: CsrfProtect = Depends()
):
    return _role_account_page(request, "dispatcher", csrf_protect)


@app.get("/account/driver", include_in_schema=False)
async def ui_account_driver(
    request: Request, csrf_protect: CsrfProtect = Depends()
):
    return _role_account_page(request, "driver", csrf_protect)

# -------------------------------------------------------

def _post_page(
    request: Request,
    csrf_protect: CsrfProtect,
    error: str = "",
    values: dict | None = None,
    status_code: int = 200,
):
    return _template_response_with_csrf(
        request,
        "post.html",
        {"jobs": list_jobs(), "error": error, "values": values or {}},
        csrf_protect,
        status_code,
    )


def _dispatcher_redirect(request: Request):
    user = current_user(request)
    if not user:
        return None, RedirectResponse("/account", status_code=303)
    if user["role"] != "dispatcher":
        return None, RedirectResponse("/account/home", status_code=303)
    return user, None




@app.get("/post", include_in_schema=False)
async def ui_post(request: Request, csrf_protect: CsrfProtect = Depends()):
    _, redirect = _dispatcher_redirect(request)
    return redirect or _post_page(request, csrf_protect)


@app.post("/post", include_in_schema=False)
async def ui_post_submit(request: Request, csrf_protect: CsrfProtect = Depends()):
    user, redirect = _dispatcher_redirect(request)
    if not user:
        return redirect
    form = await validate_form_csrf(request, csrf_protect)
    try:
        payload = _clean_job(form)
    except HTTPException as e:
        return _post_page(request, csrf_protect, e.detail, form, e.status_code)

    await _publish_job(user, payload)
    return RedirectResponse("/post", status_code=303)


@app.post("/post/delete/{message_id}", include_in_schema=False)
async def ui_post_delete(
    message_id: int, request: Request, csrf_protect: CsrfProtect = Depends()
):
    _, redirect = _dispatcher_redirect(request)
    
    if redirect:
        return redirect
    await validate_form_csrf(request, csrf_protect)
    
    if delete_job(message_id):
        await manager.broadcast(json.dumps({"type": "delete", "id": message_id}))
    return RedirectResponse("/post", status_code=303)


@app.get("/feed", include_in_schema=False)
async def ui_feed(request: Request):
    if not current_user(request):
        return RedirectResponse("/account", status_code=303)
    return templates.TemplateResponse(request, "feed.html")


@app.get("/api/get_jobs")
async def get_jobs(request: Request):
    if not current_user(request):
        raise HTTPException(status_code=401, detail="Log in to view jobs")
    return {"messages": list_jobs()}


def _clean_job(raw) -> JobPayload:
    try:
        payload = JobPayload.model_validate(raw)
    except ValidationError as e:
        raise HTTPException(
            status_code=422, detail="Invalid job details") from e

    payload.pickup_location = payload.pickup_location.strip()
    payload.dropoff_location = payload.dropoff_location.strip()
    payload.note = payload.note.strip()

    if not payload.pickup_location or not payload.dropoff_location:
        raise HTTPException(status_code=422, detail="Locations are required")

    return payload


async def _publish_job(user: dict, payload: JobPayload) -> int:
    new_id = save_job(
        user["id"],
        payload.pickup_time.isoformat(),
        payload.pickup_location,
        payload.dropoff_location,
        payload.note,
    )
    await manager.broadcast(
        json.dumps({
            "type": "message",
            "id": new_id,
            "user_id": user["id"],
            "pickup_time": payload.pickup_time.isoformat(),
            "pickup_location": payload.pickup_location,
            "dropoff_location": payload.dropoff_location,
            "note": payload.note,
        })
    )
    return new_id


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket) -> None:
    """Receive-only authenticated WebSocket for job created/deleted events."""
    if not get_user_by_token(websocket.cookies.get(AUTH_COOKIE)):
        await websocket.close(code=1008)
        return

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


def run_server() -> None:
    uvicorn.run(
        "api.app:app",
        app_dir=str(BASE_DIR),
        host="0.0.0.0",
        port=8001,
        reload=is_development,
        reload_dirs=[str(BASE_DIR)],
    )


if __name__ == "__main__":
    print("Starting relay on http://localhost:8001")
    run_server()
