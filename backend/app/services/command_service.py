"""Relay command lifecycle:  PENDING -> SENT -> ACKED | FAILED | TIMEOUT.

Feeder state is changed only by `acknowledge()` (device confirmation) or by telemetry reports.
Creating a command never changes it.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AuditLog, Device, FaultEvent, Feeder, RelayCommand, User
from ..schemas import CommandAckIn, CommandIn
from . import demo_simulator, settings_service, sms_service
from .notification_service import announce, notify
from .telemetry_service import apply_reported_relay
from .ws_manager import ws_manager

IN_FLIGHT = ("PENDING", "SENT")
EXPECTED_RELAY = {"TRIP": "RELEASED", "RESTORE": "ENERGISED"}


def create(db: Session, user: User, data: CommandIn) -> RelayCommand:
    feeder = db.get(Feeder, data.feeder_id)
    if not feeder:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown feeder")
    if settings_service.demo_mode(db):
        return _create_demo(db, user, feeder, data)
    device = feeder.device
    if not feeder.is_installed or device is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No device is installed on this feeder")
    if device.status != "ONLINE":
        raise HTTPException(status.HTTP_409_CONFLICT, "Device offline - command not sent")
    if feeder.state not in ("NORMAL", "TRIPPED"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Feeder state unknown - wait for telemetry")
    if data.action == "TRIP" and feeder.state == "TRIPPED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Feeder is already tripped")
    if data.action == "RESTORE" and feeder.state == "NORMAL":
        raise HTTPException(status.HTTP_409_CONFLICT, "Feeder is already in NORMAL state")
    busy = db.scalars(
        select(RelayCommand).where(RelayCommand.feeder_id == feeder.id, RelayCommand.status.in_(IN_FLIGHT),
            RelayCommand.is_simulated.is_(False),
        )
    ).first()
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "A command for this feeder is already awaiting acknowledgement")

    cmd = RelayCommand(
        feeder_id=feeder.id, device_id=device.id, action=data.action, source="OPERATOR",
        requested_by=user.id, status="PENDING",
    )
    db.add(cmd)
    db.add(AuditLog(user_id=user.id, action=f"COMMAND_{data.action}", detail=f"feeder={feeder.id}"))
    db.commit()
    ws_manager.publish("command", feeder_id=feeder.id)
    return cmd


def _create_demo(db: Session, user: User, feeder: Feeder, data: CommandIn) -> RelayCommand:
    """Demo Mode: validated like a live command, but acknowledged by the simulator (and labelled so)."""
    state = demo_simulator.state_for(feeder.id).state
    if data.action == "TRIP" and state == "TRIPPED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Feeder is already tripped")
    if data.action == "RESTORE" and state == "NORMAL":
        raise HTTPException(status.HTTP_409_CONFLICT, "Feeder is already in NORMAL state")
    busy = db.scalars(
        select(RelayCommand).where(
            RelayCommand.feeder_id == feeder.id, RelayCommand.status.in_(IN_FLIGHT), RelayCommand.is_simulated.is_(True)
        )
    ).first()
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "A command for this feeder is already awaiting acknowledgement")
    cmd = RelayCommand(feeder_id=feeder.id, device_id=None, action=data.action, source="OPERATOR",
                       requested_by=user.id, status="PENDING", is_simulated=True)
    db.add(cmd)
    db.add(AuditLog(user_id=user.id, action=f"DEMO_COMMAND_{data.action}", detail=f"feeder={feeder.id}"))
    db.commit()
    ws_manager.publish("command", feeder_id=feeder.id)
    return cmd


def next_for_device(db: Session, device: Device) -> RelayCommand | None:
    cmd = db.scalars(
        select(RelayCommand)
        .where(RelayCommand.device_id == device.id, RelayCommand.status == "PENDING")
        .order_by(RelayCommand.id)
        .limit(1)
    ).first()
    if cmd:
        cmd.status = "SENT"
        cmd.sent_at = datetime.now(timezone.utc)
        db.commit()
        ws_manager.publish("command", feeder_id=cmd.feeder_id)
    return cmd


def acknowledge(db: Session, device: Device, command_id: int, ack: CommandAckIn) -> RelayCommand:
    cmd = db.get(RelayCommand, command_id)
    if not cmd or cmd.device_id != device.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown command")
    if cmd.status != "SENT":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Command is {cmd.status}, cannot acknowledge")

    feeder = device.feeder
    cmd.acked_at = datetime.now(timezone.utc)
    cmd.reported_relay_state = ack.relay_state

    if ack.success and ack.relay_state == EXPECTED_RELAY[cmd.action]:
        cmd.status = "ACKED"
        apply_reported_relay(feeder, ack.relay_state)
        tripped = cmd.action == "TRIP"
        ev = FaultEvent(
            feeder_id=feeder.id, type="TRIPPED" if tripped else "RESTORED",
            severity="High" if tripped else "Low", source="OPERATOR", status="CLEARED",
            cleared_at=cmd.acked_at,
        )
        db.add(ev)
        db.flush()
        notify(
            db, kind="TRIP" if tripped else "RESTORE", severity=ev.severity, feeder_id=feeder.id, event_id=ev.id,
            title=f"{feeder.name} {'tripped' if tripped else 'restored'}",
            message="Relay state confirmed by ESP32 acknowledgement.",
        )
        sms_service.enqueue(db, "TRIPPED" if tripped else "RESTORED", feeder, event_id=ev.id, source="operator command")
    else:
        # Device said it failed, or reported a relay state that does not match the request.
        cmd.status = "FAILED"
        cmd.reason = (ack.error or "Device reported a relay state that does not match the command")[:200]
        apply_reported_relay(feeder, ack.relay_state)
        notify(
            db, kind="DEVICE", severity="High", feeder_id=feeder.id,
            title=f"{feeder.name}: {cmd.action} failed", message=cmd.reason,
        )
    db.commit()
    ws_manager.publish("command", feeder_id=feeder.id)
    ws_manager.publish("fault", feeder_id=feeder.id)
    announce()
    return cmd


def expire_stale(db: Session) -> int:
    """PENDING/SENT commands with no acknowledgement inside the window become TIMEOUT."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=get_settings().command_timeout_s)
    stale = list(
        db.scalars(select(RelayCommand).where(RelayCommand.status.in_(IN_FLIGHT), RelayCommand.created_at < cutoff))
    )
    for cmd in stale:
        cmd.status = "TIMEOUT"
        cmd.reason = "No acknowledgement from ESP32. Relay state unchanged."
        notify(
            db, kind="DEVICE", severity="High", feeder_id=cmd.feeder_id,
            title=f"Feeder {cmd.feeder_id}: {cmd.action} not acknowledged",
            message="Command timed out. Do not assume the relay operated.",
            is_simulated=cmd.is_simulated,
        )
    if stale:
        db.commit()
        ws_manager.publish("command")
        announce()
    return len(stale)
