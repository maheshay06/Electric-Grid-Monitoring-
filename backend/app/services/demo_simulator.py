"""DEMO MODE: clearly-labelled SIMULATED telemetry for when no hardware is connected.

Everything this module writes carries is_simulated=True. API reads are filtered by the Demo Mode
setting, so simulated and live data are never mixed. Simulated relay state lives in memory here and
never touches the real feeder rows. Command acknowledgement is simulated too (reported as such).
"""
import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import AIPrediction, FaultEvent, Feeder, Notification, RelayCommand, SensorReading
from . import settings_service
from .notification_service import announce, notify
from .rule_engine import evaluate
from .telemetry_service import store_prediction
from .ws_manager import ws_manager

log = logging.getLogger(__name__)

SCENARIOS = ("UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT", "ABNORMAL")
BASE_CURRENT = {1: 0.42, 2: 0.31, 3: 0.55}
SEND_DELAY_S = 0.5
ACK_DELAY_S = 1.8


@dataclass
class DemoFeeder:
    state: str = "NORMAL"  # NORMAL | TRIPPED
    scenario: str | None = None
    scenario_until: datetime | None = None


@dataclass
class DemoRuntime:
    feeders: dict[int, DemoFeeder] = field(default_factory=dict)
    drop_ack: bool = False
    ticks: int = 0


RT = DemoRuntime()


def state_for(feeder_id: int) -> DemoFeeder:
    return RT.feeders.setdefault(feeder_id, DemoFeeder())


def relay_and_load(state: str) -> tuple[str, str]:
    return ("RELEASED", "DISCONNECTED") if state == "TRIPPED" else ("ENERGISED", "CONNECTED")


def _gauss() -> float:
    return random.gauss(0, 0.5)


def sample(base: float, tripped: bool, scenario: str | None, nominal: float = 5.0) -> tuple[float, float]:
    v = nominal + _gauss() * 0.06
    i = base + _gauss() * 0.024
    if tripped:
        i = abs(_gauss()) * 0.008  # supply present, load disconnected
    elif scenario == "UNDERVOLTAGE":
        v = 4.15 + _gauss() * 0.1
    elif scenario == "OVERVOLTAGE":
        v = 5.85 + _gauss() * 0.1
    elif scenario == "OVERCURRENT":
        i = 1.9 + _gauss() * 0.16
    elif scenario == "ABNORMAL":
        v = nominal + _gauss() * 1.4
        i = base * random.uniform(0.2, 3.2)
    return min(6.0, max(0.0, v)), min(5.0, max(0.0, i))


# ------------------------------------------------------------------ lifecycle
def enable(db: Session) -> None:
    """Fresh demo run: wipes previous SIMULATED rows only, then backfills 24 h of history."""
    # Order matters: notifications reference events, predictions reference readings.
    for model, col in ((Notification, "is_simulated"), (AIPrediction, "is_simulated_input"), (FaultEvent, "is_simulated"),
                       (RelayCommand, "is_simulated"), (SensorReading, "is_simulated")):
        db.execute(delete(model).where(getattr(model, col).is_(True)))
    RT.feeders.clear()
    RT.drop_ack = False
    now = datetime.now(timezone.utc)

    rows = []
    for f in db.scalars(select(Feeder)):
        base = BASE_CURRENT.get(f.number, 0.4)
        stamps = [now - timedelta(minutes=k) for k in range(1440, 60, -1)] + [now - timedelta(seconds=10 * k) for k in range(360, 0, -1)]
        for ts in stamps:
            v, i = sample(base, False, None, f.nominal_voltage)
            rows.append(SensorReading(feeder_id=f.id, ts=ts, voltage=v, current=i, power=v * i,
                                      relay_state="ENERGISED", is_simulated=True))
    db.add_all(rows)

    f1 = db.scalars(select(Feeder).where(Feeder.number == 1)).first()
    f2 = db.scalars(select(Feeder).where(Feeder.number == 2)).first()
    past = [
        (f1, "UNDERVOLTAGE", "RULE", 5 * 3600, 4.18, "Medium", 0.42, "ACKNOWLEDGED"),
        (f2, "OVERCURRENT", "RULE", 9 * 3600, 5.0, "High", 1.88, "ACKNOWLEDGED"),
        (f2, "TRIPPED", "OPERATOR", 9 * 3600 - 60, 5.0, "High", 1.88, "CLEARED"),
        (f2, "RESTORED", "OPERATOR", 9 * 3600 - 600, 5.0, "Low", 0.31, "CLEARED"),
        (f1, "TRIPPED", "PUSHBUTTON", 20 * 3600, 5.0, "High", 0.0, "CLEARED"),
        (f1, "RESTORED", "PUSHBUTTON", 20 * 3600 - 300, 5.0, "Low", 0.42, "CLEARED"),
    ]
    for f, typ, src, ago, v, sev, i, st in past:
        if f:
            ts = now - timedelta(seconds=ago)
            db.add(FaultEvent(feeder_id=f.id, ts=ts, type=typ, severity=sev, voltage=v, current=i, source=src,
                              status=st, cleared_at=ts + timedelta(seconds=90), is_simulated=True))
    notify(db, kind="SYSTEM", severity="Low", title="Demo mode active",
           message="All values are SIMULATED. No hardware is connected.", is_simulated=True)
    db.commit()
    ws_manager.publish("settings")
    announce()


# ------------------------------------------------------------------ per-second tick
def _finish_commands(db: Session, now: datetime) -> bool:
    changed = False
    cmds = db.scalars(select(RelayCommand).where(RelayCommand.is_simulated.is_(True), RelayCommand.status.in_(("PENDING", "SENT"))))
    for c in cmds:
        age = (now - c.created_at).total_seconds()
        if c.status == "PENDING" and age >= SEND_DELAY_S:
            c.status, c.sent_at = "SENT", now
            changed = True
        elif c.status == "SENT" and age >= ACK_DELAY_S and not RT.drop_ack:
            feeder = db.get(Feeder, c.feeder_id)
            tripped = c.action == "TRIP"
            state_for(c.feeder_id).state = "TRIPPED" if tripped else "NORMAL"
            c.status, c.acked_at = "ACKED", now
            c.reported_relay_state = "RELEASED" if tripped else "ENERGISED"
            changed = True
            ev = FaultEvent(feeder_id=c.feeder_id, type="TRIPPED" if tripped else "RESTORED", severity="High" if tripped else "Low",
                            source="OPERATOR", status="CLEARED", cleared_at=now, is_simulated=True)
            db.add(ev)
            db.flush()
            notify(db, kind="TRIP" if tripped else "RESTORE", severity=ev.severity, feeder_id=c.feeder_id, event_id=ev.id,
                   title=f"{feeder.name} {'tripped' if tripped else 'restored'}",
                   message="Relay state confirmed by SIMULATED ESP32 acknowledgement.", is_simulated=True)
        # drop_ack: stays SENT until command_service.expire_stale marks it TIMEOUT
    return changed


def tick(db: Session) -> bool:
    """One simulation step. Returns False when Demo Mode is off."""
    if not settings_service.demo_mode(db):
        return False
    now = datetime.now(timezone.utc)
    RT.ticks += 1
    opened_any = False
    for f in db.scalars(select(Feeder).order_by(Feeder.number)):
        st = state_for(f.id)
        if st.scenario and st.scenario_until and now >= st.scenario_until:
            st.scenario = st.scenario_until = None
        tripped = st.state == "TRIPPED"
        v, i = sample(BASE_CURRENT.get(f.number, 0.4), tripped, st.scenario, f.nominal_voltage)
        r = SensorReading(feeder_id=f.id, ts=now, voltage=v, current=i, power=v * i,
                          relay_state="RELEASED" if tripped else "ENERGISED", is_simulated=True)
        db.add(r)
        db.flush()
        opened_any |= bool(evaluate(db, f, r, tripped=tripped))
        store_prediction(db, f, r)
    cmds_changed = _finish_commands(db, now)
    if RT.ticks % 300 == 0:  # retention: keep 25 h of simulated readings
        db.execute(delete(SensorReading).where(SensorReading.is_simulated.is_(True), SensorReading.ts < now - timedelta(hours=25)))
    db.commit()
    ws_manager.publish("telemetry")
    if cmds_changed:
        ws_manager.publish("command")
    if opened_any or cmds_changed:
        ws_manager.publish("fault")
        announce()
    return True


# ------------------------------------------------------------------ operator-driven demo actions
def inject(db: Session, feeder_id: int, scenario: str | None, seconds: int) -> None:
    st = state_for(feeder_id)
    st.scenario = scenario
    st.scenario_until = datetime.now(timezone.utc) + timedelta(seconds=seconds) if scenario else None


def pushbutton(db: Session, feeder: Feeder) -> None:
    st = state_for(feeder.id)
    st.state = "NORMAL" if st.state == "TRIPPED" else "TRIPPED"
    tripped = st.state == "TRIPPED"
    ev = FaultEvent(feeder_id=feeder.id, type="TRIPPED" if tripped else "RESTORED", severity="High" if tripped else "Low",
                    source="PUSHBUTTON", status="CLEARED", is_simulated=True)
    db.add(ev)
    db.flush()
    notify(db, kind="TRIP" if tripped else "RESTORE", severity=ev.severity, feeder_id=feeder.id, event_id=ev.id,
           title=f"{feeder.name} {'tripped' if tripped else 'restored'} (simulated pushbutton)",
           message="Local pushbutton operation reported by the SIMULATED ESP32.", is_simulated=True)
    db.commit()
    ws_manager.publish("fault", feeder_id=feeder.id)
    announce()


async def run_forever() -> None:
    while True:
        try:
            with SessionLocal() as db:
                tick(db)
        except Exception:  # never let the simulator die
            log.exception("demo tick failed")
        await asyncio.sleep(1)
