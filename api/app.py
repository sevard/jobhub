import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

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

app = FastAPI(title="Incoming WebSocket Relay", lifespan=lifespan)
app.state.development_mode = is_development

BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "ui"
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")


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
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"Client connected: {id(websocket)} (active: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"Client disconnected: {id(websocket)} (active: {len(self.active_connections)})")

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except RuntimeError as e:
                logger.warning(f"Failed to send to client {id(connection)}: {e}")
                self.disconnect(connection)
            except Exception as e:
                logger.error(f"Unexpected error broadcasting to client {id(connection)}: {e}")
                self.disconnect(connection)


manager = ConnectionManager()

AUTH_COOKIE = "auth_token"


def current_user(request: Request):
    return get_user_by_token(request.cookies.get(AUTH_COOKIE))


def _start_login(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=create_auth_session(user_id),
        httponly=True,
        samesite="lax",
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
        "note": "Websocket relay that broadcasts messages to all connected clients.",
    }

@app.get("/", include_in_schema=False)
async def ui_index(request: Request):
    if current_user(request):
        return RedirectResponse("/account/home", status_code=303)
    return templates.TemplateResponse(request, "index.html")

# --------- AUTH USER FUNCS -------------
@app.get("/account", include_in_schema=False)
async def ui_account(request: Request):
    user = current_user(request)
    if user:
        return RedirectResponse("/account/home", status_code=303)
    return templates.TemplateResponse(request, "account.html")


@app.get("/account/home", include_in_schema=False)
async def ui_account_home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/account", status_code=303)
    return RedirectResponse(f"/account/{user['role']}", status_code=303)


@app.get("/account/dispatcher", include_in_schema=False)
async def ui_account_dispatcher(request: Request):
    return _role_account_page(request, "dispatcher")


@app.get("/account/driver", include_in_schema=False)
async def ui_account_driver(request: Request):
    return _role_account_page(request, "driver")


def _role_account_page(request: Request, role: str):
    user = current_user(request)
    if not user:
        return RedirectResponse("/account", status_code=303)
    if user["role"] != role:
        return RedirectResponse(f"/account/{user['role']}", status_code=303)
    return templates.TemplateResponse(request, f"account_{role}.html", {"user": user})


@app.post("/api/signup", status_code=201)
async def signup(payload: SignupPayload, response: Response):
    user_id = create_user(payload.username, payload.password, payload.role)
    if user_id is None:
        raise HTTPException(status_code=409, detail="Username is already taken")
    _start_login(response, user_id)
    return {"status": "ok", "username": payload.username, "role": payload.role}


@app.post("/api/login")
async def login(payload: Credentials, response: Response):
    user_id = verify_user(payload.username, payload.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    _start_login(response, user_id)
    return {"status": "ok", "username": payload.username}


@app.post("/api/logout")
async def logout(request: Request, response: Response):
    delete_auth_session(request.cookies.get(AUTH_COOKIE))
    response.delete_cookie(AUTH_COOKIE)
    return {"status": "ok"}
# -------------------------------------------------------

def require_dispatcher(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Log in to continue")
    if user["role"] != "dispatcher":
        raise HTTPException(status_code=403, detail="Only dispatchers can do this")
    return user


@app.get("/post", include_in_schema=False)
async def ui_post(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/account", status_code=303)
    if user["role"] != "dispatcher":
        return RedirectResponse("/account/home", status_code=303)
    return templates.TemplateResponse(request, "post.html")


@app.get("/feed", include_in_schema=False)
async def ui_feed(request: Request):
    if not current_user(request):
        return RedirectResponse("/account", status_code=303)
    return templates.TemplateResponse(request, "feed.html")


@app.get("/api/get_jobs")
async def messages(request: Request):
    if not current_user(request):
        raise HTTPException(status_code=401, detail="Log in to view jobs")

    return {"messages": list_jobs()}


@app.post("/api/post_job")
async def create_message(payload: JobPayload, request: Request):
    user = require_dispatcher(request)

    new_id = save_job(
        user["id"], 
        payload.pickup_time.isoformat(), 
        payload.pickup_location, 
        payload.dropoff_location,
        payload.note
    )
    
    await manager.broadcast(
        json.dumps({
            "type": "message", 
            "id": new_id,
            "user_id": user["id"],
            "pickup_time": payload.pickup_time.isoformat(),
            "pickup_location": payload.pickup_location,
            "dropoff_location": payload.dropoff_location,
            "note": payload.note
        })
    )
    return {"status": "ok", "id": new_id}


@app.delete("/api/delete_job/{message_id}")
async def remove_message(message_id: int, request: Request):
    require_dispatcher(request)

    if not delete_job(message_id):
        raise HTTPException(status_code=404, detail="Message not found")

    await manager.broadcast(json.dumps({"type": "delete", "id": message_id}))
    return {"status": "ok"}


async def _websocket_relay_impl(websocket: WebSocket):
    if not get_user_by_token(websocket.cookies.get(AUTH_COOKIE)):
        await websocket.close(code=1008)
        return
    await manager.connect(websocket)
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
    finally:
        manager.disconnect(websocket)


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket):
    await _websocket_relay_impl(websocket)


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
    print("Starting relay on http://localhost:8001 and ws://localhost:8001/ws")
    run_server()
