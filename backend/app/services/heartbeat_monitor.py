import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import SessionLocal
from ..models import Device, FaultEvent
from . import command_service, sms_service
from .notification_service import announce, notify
from .ws_manager import ws_manager

log = logging.getLogger(__name__)


def sweep_devices(db: Session) -> int:
    """Marks silent devices OFFLINE and raises a DEVICE_OFFLINE event + notification."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=get_settings().heartbeat_timeout_s)
    gone = [
        d for d in db.scalars(select(Device).where(Device.status == "ONLINE"))
        if d.last_heartbeat_at is None or d.last_heartbeat_at < cutoff
    ]
    for d in gone:
        d.status = "OFFLINE"
        d.feeder.state = "OFFLINE"
        d.feeder.relay_state = "UNKNOWN"  # we no longer know what the relay is doing
        d.feeder.load_state = "UNKNOWN"
        ev = FaultEvent(feeder_id=d.feeder_id, type="DEVICE_OFFLINE", severity="High", source="SYSTEM", status="ACTIVE")
        db.add(ev)
        db.flush()
        notify(
            db, kind="DEVICE", severity="High", feeder_id=d.feeder_id, event_id=ev.id,
            title=f"{d.name} disconnected", message="No heartbeat from ESP32. Check Wi-Fi and power supply.",
        )
        sms_service.enqueue(db, "DEVICE_OFFLINE", d.feeder, event_id=ev.id)
    if gone:
        db.commit()
        ws_manager.publish("fault")
        announce()
    return len(gone)


async def run_forever() -> None:
    while True:
        try:
            with SessionLocal() as db:
                sweep_devices(db)
                command_service.expire_stale(db)
        except Exception:  # never let the monitor die
            log.exception("monitor sweep failed")
        await asyncio.sleep(3)
