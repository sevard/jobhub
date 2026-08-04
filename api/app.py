import json
import os
import sys
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import the database functions after modifying sys.path
from api.db import delete_message, init_db, list_messages, save_message

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
        print(f"Client connected: {id(websocket)} (active: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"Client disconnected: {id(websocket)} (active: {len(self.active_connections)})")

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
async def messages():
    return {"messages": list_messages()}


@app.post("/post_message")
async def create_message(payload: MessagePayload):
    new_id = save_message(payload.content)
    await manager.broadcast(
        json.dumps({"type": "message", "id": new_id, "content": payload.content})
    )
    return {"status": "ok", "id": new_id}


@app.delete("/delete_message/{message_id}")
async def remove_message(message_id: int):
    if not delete_message(message_id):
        raise HTTPException(status_code=404, detail="Message not found")
    await manager.broadcast(json.dumps({"type": "delete", "id": message_id}))
    return {"status": "ok"}


async def _websocket_relay_impl(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            incoming = await websocket.receive_text()
            try:
                normalized = json.dumps(json.loads(incoming))
            except json.JSONDecodeError:
                normalized = incoming
            new_id = save_message(normalized)
            await manager.broadcast(
                json.dumps({"type": "message", "id": new_id, "content": normalized})
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket):
    await _websocket_relay_impl(websocket)


@app.websocket("/ws/")
async def websocket_relay_slash(websocket: WebSocket):
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
