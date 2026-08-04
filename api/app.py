from api.db import delete_message, get_message_session_id, init_db, list_messages, save_message
import json
import os
import sys
import uuid
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import the database functions after modifying sys.path

is_development = os.getenv("APP_ENV", "production").lower() == "development"

app = FastAPI(title="Incoming WebSocket Relay")
app.state.development_mode = is_development

FRONTEND_DIR = BASE_DIR / "frontend" / "relay-ui"

init_db()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(
            f"Client connected: {id(websocket)} (active: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(
                f"Client disconnected: {id(websocket)} (active: {len(self.active_connections)})")

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


@app.get("/")
async def root():
    return {
        "service": "relay-backend",
        "status": "running",
        "websocket_endpoints": ["/ws", "/ws/"],
        "development_mode": app.state.development_mode,
        "note": "Websocket relay that broadcasts messages to all connected clients.",
    }


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> None:
    return None


class MessagePayload(BaseModel):
    content: str


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/get_message")
async def messages(request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)

    return {
        "messages": list_messages(),
        "my_session_id": session_id
    }


@app.post("/post_message")
async def create_message(payload: MessagePayload, request: Request, response: Response):
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(key="session_id", value=session_id)

    new_id = save_message(session_id, payload.content)
    await manager.broadcast(
        json.dumps({"type": "message", "id": new_id,
                   "session_id": session_id, "content": payload.content})
    )
    return {"status": "ok", "id": new_id}


@app.delete("/delete_message/{message_id}")
async def remove_message(message_id: int, request: Request):
    session_id = request.cookies.get("session_id")
    message_session = get_message_session_id(message_id)

    if not message_session:
        raise HTTPException(status_code=404, detail="Message not found")

    if session_id != message_session:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message")

    if not delete_message(message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    await manager.broadcast(json.dumps({"type": "delete", "id": message_id}))
    return {"status": "ok"}


async def _websocket_relay_impl(websocket: WebSocket):
    await manager.connect(websocket)
    # The websocket connect doesn't automatically issue new session_ids since it's hard to set cookies mid-upgrade,
    # but the browser will send the existing session_id cookie if it has one. For pure relay, we just
    # broadcast whatever comes in, though in the UI we no longer send from websockets anyway.
    try:
        while True:
            incoming = await websocket.receive_text()
            try:
                normalized = json.dumps(json.loads(incoming))
            except json.JSONDecodeError:
                normalized = incoming

            # Since pure websocket clients might not have a session cookie handled by request.cookies,
            # we assign a fallback anonymous session_id just for websocket-originated saves.
            ws_session_id = websocket.cookies.get(
                "session_id", str(uuid.uuid4()))
            new_id = save_message(ws_session_id, normalized)
            await manager.broadcast(
                json.dumps({"type": "message", "id": new_id,
                           "session_id": ws_session_id, "content": normalized})
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket):
    await _websocket_relay_impl(websocket)


# Mounted last so it never shadows the API routes defined above.
app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


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
