import asyncio
import contextlib
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool

from api.auth import decode_access_token, get_user_from_payload
from api.config import AUTH_COOKIE
from api.db import pool

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


def _token_expiry(token: str | None) -> float | None:
    """When the login token expires (epoch seconds), or None if it does not belong to a user."""
    payload = decode_access_token(token)
    if payload is None or payload.get("exp") is None:
        return None
    # A short-lived lookup: the connection must not be held for the life of the socket
    with pool.connection() as connection:
        if get_user_from_payload(connection, payload) is None:
            return None
    return float(payload["exp"])


@router.websocket("/ws")
async def websocket_relay(websocket: WebSocket) -> None:
    """Receive-only event stream for logged-in users.

    The login cookie is checked before the handshake is accepted, and the
    connection is closed when that token expires. Client messages are discarded.
    """
    expires_at = await run_in_threadpool(_token_expiry, websocket.cookies.get(AUTH_COOKIE))
    if expires_at is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(websocket)
    try:
        async with asyncio.timeout(max(expires_at - time.time(), 0)):
            while True:
                await websocket.receive_text()
    except TimeoutError:
        with contextlib.suppress(RuntimeError):
            await websocket.close(
                code=status.WS_1008_POLICY_VIOLATION, reason="Session expired"
            )
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
