import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from api.db import delete_job, get_job_session_id, init_db, list_jobs, save_job

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
@app.get("/ui/index.html", include_in_schema=False)
async def ui_index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/post", include_in_schema=False)
@app.get("/ui/post.html", include_in_schema=False)
async def ui_post(request: Request):
    return templates.TemplateResponse(request, "post.html")


@app.get("/feed", include_in_schema=False)
@app.get("/ui/feed.html", include_in_schema=False)
async def ui_feed(request: Request):
    return templates.TemplateResponse(request, "feed.html")


@app.get("/api/get_message")
async def messages(request: Request, response: Response, own_only: bool = False):

    session_id = request.cookies.get("session_id")

    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)

    if own_only:
        db_messages = list_jobs(session_id)
    else:
        db_messages = list_jobs()

    return {
        "messages": db_messages,
        "my_session_id": session_id
    }


@app.post("/api/post_message")
async def create_message(payload: JobPayload, request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)

    new_id = save_job(
        session_id, 
        payload.pickup_time.isoformat(), 
        payload.pickup_location, 
        payload.dropoff_location,
        payload.note
    )
    
    await manager.broadcast(
        json.dumps({
            "type": "message", 
            "id": new_id,
            "session_id": session_id,
            "pickup_time": payload.pickup_time.isoformat(),
            "pickup_location": payload.pickup_location,
            "dropoff_location": payload.dropoff_location,
            "note": payload.note
        })
    )
    return {"status": "ok", "id": new_id}


@app.delete("/api/delete_message/{message_id}")
async def remove_message(message_id: int, request: Request):
    session_id = request.cookies.get("session_id")
    message_session = get_job_session_id(message_id)

    if not message_session:
        raise HTTPException(status_code=404, detail="Message not found")

    if session_id != message_session:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message")

    if not delete_job(message_id):
        raise HTTPException(status_code=404, detail="Message not found")

    await manager.broadcast(json.dumps({"type": "delete", "id": message_id}))
    return {"status": "ok"}


async def _websocket_relay_impl(websocket: WebSocket):
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
