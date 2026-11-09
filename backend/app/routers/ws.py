import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..deps import user_from_token
from ..services.ws_manager import ws_manager

router = APIRouter()


@router.websocket("/ws/live")
async def live(ws: WebSocket):
    """Auth is the first message ({"type":"auth","token":...}) so the JWT never appears in a URL or access log."""
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
        with SessionLocal() as db:
            ok = first.get("type") == "auth" and user_from_token(db, first.get("token")) is not None
    except (asyncio.TimeoutError, ValueError, WebSocketDisconnect, AttributeError):
        ok = False
    if not ok:
        await ws.close(code=4401)
        return
    ws_manager.register(ws)
    await ws.send_text(json.dumps({"type": "ready"}))
    try:
        while True:
            await ws.receive_text()  # clients may send pings; content is ignored
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect(ws)
