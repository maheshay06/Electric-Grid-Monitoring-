"""Endpoints called by the ESP32 (auth: X-Device-Key). Base path /api/device."""
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import current_device
from ..models import Device, FaultEvent
from ..schemas import CommandAckIn, DeviceCommandOut, DeviceEventIn, HeartbeatIn, TelemetryIn
from ..services import command_service, sms_service, telemetry_service
from ..services.notification_service import announce, notify
from ..services.ws_manager import ws_manager

router = APIRouter(prefix="/api/device", tags=["device"])


@router.post("/telemetry", status_code=202)
def telemetry(body: TelemetryIn, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    # Out-of-range / NaN / inconsistent payloads are rejected with 422 by TelemetryIn and never stored.
    telemetry_service.ingest(db, device, body)
    return {"status": "accepted"}


@router.post("/heartbeat", status_code=202)
def heartbeat(body: HeartbeatIn, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    came_back = telemetry_service.mark_alive(db, device, body)
    db.commit()
    if came_back:
        ws_manager.publish("fault", feeder_id=device.feeder_id)
        announce()
    return {"status": "ok"}


@router.get("/commands/next")
def next_command(response: Response, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    telemetry_service.mark_alive(db, device)
    cmd = command_service.next_for_device(db, device)
    if cmd is None:
        db.commit()
        response.status_code = 204
        return None
    return DeviceCommandOut(id=cmd.id, action=cmd.action)


@router.post("/commands/{command_id}/ack")
def ack(command_id: int, body: CommandAckIn, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    cmd = command_service.acknowledge(db, device, command_id, body)
    return {"status": cmd.status}


@router.post("/events", status_code=202)
def event(body: DeviceEventIn, device: Device = Depends(current_device), db: Session = Depends(get_db)):
    """Local pushbutton operation / boot, reported by the device. The button works without the dashboard."""
    feeder = device.feeder
    telemetry_service.mark_alive(db, device)
    telemetry_service.apply_reported_relay(feeder, body.relay_state)
    if body.type in ("PUSHBUTTON_TRIP", "PUSHBUTTON_RESTORE"):
        tripped = body.type == "PUSHBUTTON_TRIP"
        ev = FaultEvent(
            feeder_id=feeder.id, type="TRIPPED" if tripped else "RESTORED", severity="High" if tripped else "Low",
            source="PUSHBUTTON", status="CLEARED",
        )
        db.add(ev)
        db.flush()
        notify(
            db, kind="TRIP" if tripped else "RESTORE", severity=ev.severity, feeder_id=feeder.id, event_id=ev.id,
            title=f"{feeder.name} {'tripped' if tripped else 'restored'} (local pushbutton)",
            message="Local pushbutton operation reported by the ESP32.",
        )
        sms_service.enqueue(db, "TRIPPED" if tripped else "RESTORED", feeder, event_id=ev.id, source="local pushbutton")
    elif body.type == "BOOT":
        sms_service.enqueue(db, "BOOT", feeder)
    db.commit()
    ws_manager.publish("fault", feeder_id=feeder.id)
    announce()
    return {"status": "accepted"}
