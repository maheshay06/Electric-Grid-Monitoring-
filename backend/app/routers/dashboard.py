from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_user
from ..models import Device, FaultEvent, Feeder, Notification, SensorReading, User
from ..services.feeder_view import feeder_out
from ..services import settings_service
from ..services.ai_service import model_available

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(user: User = Depends(current_user), db: Session = Depends(get_db)):
    demo = settings_service.demo_mode(db)
    feeders = []
    for f in db.scalars(select(Feeder).order_by(Feeder.number)):
        last = db.scalars(
            select(SensorReading).where(SensorReading.feeder_id == f.id, SensorReading.is_simulated == demo)
            .order_by(SensorReading.id.desc()).limit(1)
        ).first()
        feeders.append({
            **feeder_out(db, f, demo).model_dump(mode="json"),
            "latest": None if last is None else {
                "ts": last.ts.isoformat(), "voltage": last.voltage, "current": last.current, "power": last.power,
            },
            "device_status": "SIMULATED" if demo else (f.device.status if f.device else None),
        })
    active = db.scalar(select(func.count()).select_from(FaultEvent).where(
        FaultEvent.status == "ACTIVE", FaultEvent.is_simulated == demo)) or 0
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.read_at.is_(None), Notification.is_simulated == demo, (Notification.user_id.is_(None)) | (Notification.user_id == user.id))) or 0
    devices = list(db.scalars(select(Device)))
    return {
        "server_time": datetime.now(timezone.utc).isoformat(),
        "demo_mode": demo,
        "feeders": feeders,
        "active_faults": active,
        "unread_notifications": unread,
        "esp32_online": (not demo) and any(d.status == "ONLINE" for d in devices),
        "model_available": model_available(),
        "system_health": "FAULT" if active else "OPTIMAL",
    }
