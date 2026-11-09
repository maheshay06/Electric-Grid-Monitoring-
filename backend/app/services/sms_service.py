"""SMS alerting (Twilio). Event-based, rate-limited, never for simulated data.

Rules taken from the project report (section 7.2):
  * an alert is sent only when its event is detected;
  * a message never claims the relay physically opened/closed - it says what the ESP32 REPORTED;
  * repeat alerts for the same event are suppressed inside an interval, never sent continuously;
  * messages carry system name, feeder, event type, V/I/P, date-time and relay/system status.

Events are written to an outbox table (one row per recipient); sms_worker sends them. Enqueueing is
cheap and never raises into the telemetry path.
"""
import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Feeder, SensorReading, SmsMessage, SmsRecipient
from . import settings_service

log = logging.getLogger(__name__)

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
STATE_CHANGE_KINDS = {"TRIPPED", "RESTORED"}


def mask(number: str | None) -> str:
    if not number:
        return "-"
    return number[:3] + "*" * max(0, len(number) - 5) + number[-2:]


def is_enabled(db: Session) -> bool:
    return get_settings().sms_configured and settings_service.get(db, "sms_enabled", "false") == "true"


def _stamp() -> str:
    s = get_settings()
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(s.sms_timezone)
    except Exception:  # unknown zone or no tzdata: fall back to UTC and say so
        tz = timezone.utc
    now = datetime.now(tz)
    return now.strftime("%d-%b %H:%M ") + (now.tzname() or "UTC")


def _latest(db: Session, feeder: Feeder) -> SensorReading | None:
    return db.scalars(
        select(SensorReading).where(SensorReading.feeder_id == feeder.id, SensorReading.is_simulated.is_(False))
        .order_by(SensorReading.id.desc()).limit(1)
    ).first()


def build_message(kind: str, feeder: Feeder, v: float | None, i: float | None, p: float | None, source: str = "") -> str:
    """Plain ASCII (GSM-7) so a message stays one 160-char segment where possible."""
    name = get_settings().sms_system_name
    vals = "" if v is None or i is None else f" V={v:.2f}V I={i:.2f}A P={(p if p is not None else v * i):.2f}W."
    t = _stamp()
    f = feeder.name
    if kind == "BOOT":
        return f"{name}: {f} controller started. Relay {feeder.relay_state}, status {feeder.state}.{vals} {t}"
    if kind == "TRIPPED":
        return (f"ALERT {name}: {f} reported TRIPPED by the ESP32 ({source or 'command'}). Relay state: RELEASED."
                f"{vals} {t}. Please check the system.")
    if kind == "RESTORED":
        return f"{name}: {f} reported RESTORED to NORMAL by the ESP32 ({source or 'command'}). Relay state: ENERGISED.{vals} {t}"
    if kind in ("UNDERVOLTAGE", "OVERVOLTAGE"):
        return f"VOLTAGE ALERT {name}: {f} {kind}.{vals} {t}. Please inspect the supply."
    if kind == "OVERCURRENT":
        return f"CURRENT ALERT {name}: {f} OVERCURRENT.{vals} {t}. Please inspect the load."
    if kind == "DEVICE_OFFLINE":
        return f"WARNING {name}: Communication with the {f} controller (ESP32) is lost. Check the ESP32, Wi-Fi and power. {t}"
    if kind == "TEST":
        return f"{name}: Test message. SMS alerts are configured. {t}"
    raise ValueError(f"no SMS template for {kind}")


def enqueue(
    db: Session, kind: str, feeder: Feeder, *, simulated: bool = False, event_id: int | None = None,
    source: str = "", v: float | None = None, i: float | None = None, p: float | None = None,
    force: bool = False, only_recipient_id: int | None = None,
) -> int:
    """Adds outbox rows to the session (caller commits). Returns the number of QUEUED rows."""
    if simulated:  # Demo Mode data must never cost money or alarm real people
        return 0
    try:
        if not force and not is_enabled(db):
            return 0
        q = select(SmsRecipient).where(SmsRecipient.is_active.is_(True))
        if only_recipient_id:
            q = q.where(SmsRecipient.id == only_recipient_id)
        recipients = list(db.scalars(q))
        if not recipients:
            return 0

        s = get_settings()
        interval = s.sms_state_change_interval_s if kind in STATE_CHANGE_KINDS else s.sms_repeat_interval_s
        if not force:
            since = datetime.now(timezone.utc) - timedelta(seconds=interval)
            recent = db.scalars(
                select(SmsMessage).where(
                    SmsMessage.kind == kind, SmsMessage.feeder_id == feeder.id,
                    SmsMessage.status != "SKIPPED", SmsMessage.created_at >= since,
                ).limit(1)
            ).first()
            if recent:
                db.add(SmsMessage(kind=kind, feeder_id=feeder.id, event_id=event_id, body="", status="SKIPPED",
                                  error=f"repeat suppressed (same event within {interval}s)"))
                return 0

        if v is None or i is None:
            last = _latest(db, feeder)
            if last:
                v, i, p = last.voltage, last.current, last.power
        body = build_message(kind, feeder, v, i, p, source)
        for r in recipients:
            db.add(SmsMessage(kind=kind, feeder_id=feeder.id, event_id=event_id, to_number=r.phone, body=body,
                              status="QUEUED", is_test=(kind == "TEST")))
        return len(recipients)
    except Exception:  # alerting must never break telemetry ingestion or command handling
        log.exception("failed to enqueue SMS for %s", kind)
        return 0
