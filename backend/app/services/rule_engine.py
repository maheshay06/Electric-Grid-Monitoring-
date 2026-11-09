"""Deterministic threshold fault detection. Separate from, and independent of, the ML classifier.

A fault opens only after two consecutive violating readings (filters single ADC spikes) and closes
after two consecutive clean readings. Detection NEVER trips the relay: it raises events and
notifications for the operator.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Feeder, FaultEvent, SensorReading
from . import sms_service
from .notification_service import notify

RULE_TYPES = ("UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT")


def violation(feeder: Feeder, voltage: float, current: float) -> str | None:
    if current > feeder.oc_threshold:
        return "OVERCURRENT"
    if voltage < feeder.uv_threshold:
        return "UNDERVOLTAGE"
    if voltage > feeder.ov_threshold:
        return "OVERVOLTAGE"
    return None


def _open_faults(db: Session, feeder_id: int, simulated: bool) -> list[FaultEvent]:
    return list(
        db.scalars(
            select(FaultEvent).where(
                FaultEvent.feeder_id == feeder_id,
                FaultEvent.source == "RULE",
                FaultEvent.is_simulated == simulated,
                FaultEvent.status.in_(("ACTIVE", "ACKNOWLEDGED")),
            )
        )
    )


def evaluate(db: Session, feeder: Feeder, reading: SensorReading, tripped: bool | None = None) -> list[FaultEvent]:
    """Call after `reading` is flushed. Returns newly opened events.

    `tripped` overrides the feeder row (demo mode keeps its own simulated state)."""
    tripped = (feeder.state == "TRIPPED") if tripped is None else tripped
    prev = db.scalars(
        select(SensorReading)
        .where(SensorReading.feeder_id == feeder.id, SensorReading.id < reading.id,
               SensorReading.is_simulated == reading.is_simulated)
        .order_by(SensorReading.id.desc())
        .limit(1)
    ).first()

    now_v = None if tripped else violation(feeder, reading.voltage, reading.current)
    prev_v = None if prev is None or tripped else violation(feeder, prev.voltage, prev.current)
    open_faults = _open_faults(db, feeder.id, reading.is_simulated)
    opened: list[FaultEvent] = []

    for ftype in RULE_TYPES:
        existing = next((f for f in open_faults if f.type == ftype), None)
        if now_v == ftype and prev_v == ftype and existing is None:
            ev = FaultEvent(
                feeder_id=feeder.id, type=ftype, severity="High" if ftype == "OVERCURRENT" else "Medium",
                voltage=reading.voltage, current=reading.current, source="RULE", status="ACTIVE",
                is_simulated=reading.is_simulated,
            )
            db.add(ev)
            db.flush()
            notify(
                db, kind="FAULT", severity=ev.severity, feeder_id=feeder.id, event_id=ev.id,
                title=f"{feeder.name}: {ftype}",
                message=f"Measured {reading.voltage:.2f} V / {reading.current:.3f} A. "
                        "Operator review recommended — no automatic trip.",
                is_simulated=reading.is_simulated,
            )
            sms_service.enqueue(db, ftype, feeder, simulated=reading.is_simulated, event_id=ev.id,
                                v=reading.voltage, i=reading.current, p=reading.power)
            opened.append(ev)
        elif existing is not None and now_v != ftype and prev_v != ftype:
            existing.status = "CLEARED"
            existing.cleared_at = datetime.now(timezone.utc)
    return opened
