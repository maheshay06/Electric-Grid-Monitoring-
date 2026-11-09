"""SQLAlchemy models. All datetimes are stored as UTC and returned timezone-aware."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite drops tzinfo; normalise to UTC on the way in and re-attach it on the way out."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    operator_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="operator")  # admin | operator | viewer
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to invalidate all issued JWTs
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    location: Mapped[Location] = relationship()


class Feeder(Base):
    __tablename__ = "feeders"
    __table_args__ = (UniqueConstraint("location_id", "number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    is_installed: Mapped[bool] = mapped_column(Boolean, default=False)
    nominal_voltage: Mapped[float] = mapped_column(Float, default=5.0)
    uv_threshold: Mapped[float] = mapped_column(Float, default=4.5)
    ov_threshold: Mapped[float] = mapped_column(Float, default=5.5)
    oc_threshold: Mapped[float] = mapped_column(Float, default=1.5)
    # State is what the device REPORTED, never what a command requested.
    state: Mapped[str] = mapped_column(String(16), default="OFFLINE")  # NORMAL|TRIPPED|OFFLINE|NOT_INSTALLED
    relay_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # ENERGISED|RELEASED|UNKNOWN
    load_state: Mapped[str] = mapped_column(String(16), default="UNKNOWN")  # CONNECTED|DISCONNECTED|UNKNOWN
    state_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    location: Mapped[Location] = relationship()
    device: Mapped["Device | None"] = relationship(back_populates="feeder", uselist=False)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    hw_model: Mapped[str] = mapped_column(String(64), default="ESP32 DevKit V1")
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    wifi_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="OFFLINE")  # ONLINE | OFFLINE
    calibration_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    feeder: Mapped[Feeder] = relationship(back_populates="device")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (Index("ix_readings_feeder_ts", "feeder_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    power: Mapped[float] = mapped_column(Float)
    relay_state: Mapped[str] = mapped_column(String(16))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class FaultEvent(Base):
    __tablename__ = "fault_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"), index=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    type: Mapped[str] = mapped_column(String(24))
    severity: Mapped[str] = mapped_column(String(12))
    voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    current: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16))  # RULE | OPERATOR | PUSHBUTTON | SYSTEM
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE | ACKNOWLEDGED | CLEARED
    cleared_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class AIPrediction(Base):
    __tablename__ = "ai_predictions"
    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"), index=True)
    reading_id: Mapped[int | None] = mapped_column(ForeignKey("sensor_readings.id"), nullable=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    predicted_class: Mapped[str] = mapped_column(String(24))
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(12))
    model_version: Mapped[str] = mapped_column(String(32))
    voltage: Mapped[float] = mapped_column(Float)
    current: Mapped[float] = mapped_column(Float)
    power: Mapped[float] = mapped_column(Float)
    # Fixed by design: the model is trained on synthetic data and its output can never drive hardware.
    is_synthetic_model: Mapped[bool] = mapped_column(Boolean, default=True)
    advisory_only: Mapped[bool] = mapped_column(Boolean, default=True)
    is_simulated_input: Mapped[bool] = mapped_column(Boolean, default=False)


class RelayCommand(Base):
    __tablename__ = "relay_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    feeder_id: Mapped[int] = mapped_column(ForeignKey("feeders.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True)  # None = demo command
    action: Mapped[str] = mapped_column(String(8))  # TRIP | RESTORE
    source: Mapped[str] = mapped_column(String(16), default="OPERATOR")  # no ML source exists
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="PENDING")  # PENDING|SENT|ACKED|FAILED|TIMEOUT
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reported_relay_state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # None = broadcast
    feeder_id: Mapped[int | None] = mapped_column(ForeignKey("feeders.id"), nullable=True)
    related_event_id: Mapped[int | None] = mapped_column(ForeignKey("fault_events.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(12))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str] = mapped_column(String(400), default="")


class SmsRecipient(Base):
    __tablename__ = "sms_recipients"
    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), unique=True)  # E.164
    label: Mapped[str] = mapped_column(String(60), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SmsMessage(Base):
    """Outbox: one row per recipient. SENT means Twilio accepted it, not that the handset received it."""

    __tablename__ = "sms_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    kind: Mapped[str] = mapped_column(String(24))
    feeder_id: Mapped[int | None] = mapped_column(ForeignKey("feeders.id"), nullable=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("fault_events.id"), nullable=True)
    to_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    body: Mapped[str] = mapped_column(String(480), default="")
    status: Mapped[str] = mapped_column(String(10), default="QUEUED", index=True)  # QUEUED|SENT|FAILED|SKIPPED
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    twilio_sid: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
