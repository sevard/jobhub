import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


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


@router.websocket("/ws")
async def websocket_relay(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
