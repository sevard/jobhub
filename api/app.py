import json
from typing import List

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="Incoming WebSocket Relay")


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

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
        "note": "Simple websocket relay that broadcasts messages to all connected \
            clients. Messages are normalized to JSON if possible.",
    }


@app.get("/health")
async def health():
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
            await manager.broadcast(normalized)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.websocket("/ws")
async def websocket_relay(websocket: WebSocket):
    await _websocket_relay_impl(websocket)


@app.websocket("/ws/")
async def websocket_relay_slash(websocket: WebSocket):
    await _websocket_relay_impl(websocket)


if __name__ == "__main__":
    print("Starting relay on http://localhost:8001 and ws://localhost:8001/ws")
    uvicorn.run(app, host="0.0.0.0", port=8001)
