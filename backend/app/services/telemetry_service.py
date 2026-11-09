from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AIPrediction, Device, FaultEvent, Feeder, SensorReading
from ..schemas import HeartbeatIn, TelemetryIn
from . import ai_service
from .notification_service import announce, notify
from .rule_engine import evaluate
from .ws_manager import ws_manager

STATE_FROM_RELAY = {
    "ENERGISED": ("NORMAL", "CONNECTED"),
    "RELEASED": ("TRIPPED", "DISCONNECTED"),
}


def apply_reported_relay(feeder: Feeder, relay_state: str) -> None:
    """The ONLY way feeder state changes: the device reported it."""
    state, load = STATE_FROM_RELAY[relay_state]
    feeder.relay_state = relay_state
    feeder.load_state = load
    feeder.state = state
    feeder.state_updated_at = datetime.now(timezone.utc)


def mark_alive(db: Session, device: Device, hb: HeartbeatIn | None = None) -> bool:
    """Records liveness. Returns True if the device just came back online."""
    came_back = device.status != "ONLINE"
    device.last_heartbeat_at = datetime.now(timezone.utc)
    device.status = "ONLINE"
    if hb:
        device.firmware_version = hb.firmware_version or device.firmware_version
        device.wifi_rssi = hb.wifi_rssi if hb.wifi_rssi is not None else device.wifi_rssi
        device.ip_address = hb.ip_address or device.ip_address
    if came_back:
        for ev in db.scalars(
            select(FaultEvent).where(
                FaultEvent.feeder_id == device.feeder_id,
                FaultEvent.type == "DEVICE_OFFLINE",
                FaultEvent.status.in_(("ACTIVE", "ACKNOWLEDGED")),
            )
        ):
            ev.status = "CLEARED"
            ev.cleared_at = datetime.now(timezone.utc)
        notify(
            db, kind="DEVICE", severity="Low", feeder_id=device.feeder_id,
            title=f"{device.name} connected", message="ESP32 is online and reporting.",
        )
    return came_back


def store_prediction(db: Session, feeder: Feeder, reading: SensorReading) -> None:
    """Advisory ML result, stored for display only (None until a model exists).

    A row is updated in place while the class is unchanged for 5 s, so history stays compact but
    "latest" is always fresh. A new ABNORMAL CONDITION episode raises an advisory notification."""
    pred = ai_service.predict(reading.voltage, reading.current, reading.power)
    if not pred:
        return
    last = db.scalars(
        select(AIPrediction)
        .where(AIPrediction.feeder_id == feeder.id, AIPrediction.is_simulated_input == reading.is_simulated)
        .order_by(AIPrediction.id.desc()).limit(1)
    ).first()
    now = datetime.now(timezone.utc)
    fields = dict(reading_id=reading.id, voltage=reading.voltage, current=reading.current, power=reading.power, ts=now, **pred)
    if last and last.predicted_class == pred["predicted_class"] and (now - last.ts).total_seconds() < 5:
        for k, v in fields.items():
            setattr(last, k, v)
        return
    db.add(AIPrediction(feeder_id=feeder.id, is_simulated_input=reading.is_simulated, **fields))
    if pred["predicted_class"] == "ABNORMAL CONDITION":
        notify(
            db, kind="AI_ADVISORY", severity="Medium", feeder_id=feeder.id, is_simulated=reading.is_simulated,
            title=f"{feeder.name}: AI flags abnormal condition",
            message="Advisory only (synthetic demo model). Verify measurements before taking any action.",
        )


def ingest(db: Session, device: Device, data: TelemetryIn) -> SensorReading:
    feeder = device.feeder
    came_back = mark_alive(db, device)
    reading = SensorReading(
        feeder_id=feeder.id, device_id=device.id, voltage=data.voltage, current=data.current,
        power=data.power if data.power is not None else data.voltage * data.current,
        relay_state=data.relay_state, is_simulated=False,
    )
    db.add(reading)
    db.flush()
    apply_reported_relay(feeder, data.relay_state)
    opened = evaluate(db, feeder, reading)

    store_prediction(db, feeder, reading)
    db.commit()

    ws_manager.publish("telemetry", feeder_id=feeder.id)
    if opened or came_back:
        ws_manager.publish("fault", feeder_id=feeder.id)
        announce()
    return reading
