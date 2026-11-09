"""Fan-out of live events to browser WebSocket clients.

`publish()` is safe to call from sync request handlers (worker threads) and async tasks alike.
Messages carry only a type and ids — clients re-fetch authoritative data over REST.
"""
import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class WSManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self, ws: WebSocket) -> None:
        """Called after the socket is accepted AND authenticated."""
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def _broadcast(self, message: str) -> None:
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:  # client went away
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish(self, event_type: str, **data) -> None:
        if not self._loop or not self._clients:
            return
        msg = json.dumps({"type": event_type, **data})
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)
        except RuntimeError:
            log.debug("event loop closed; dropping %s", event_type)


ws_manager = WSManager()
