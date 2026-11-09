from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

from .config import get_settings

Role = Literal["admin", "operator", "viewer"]
RelayStateIn = Literal["ENERGISED", "RELEASED"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------- auth ----------------
class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operator_id: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=32)


class UserOut(ORM):
    operator_id: str
    full_name: str
    role: Role
    location_code: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------------- feeders ----------------
class FeederOut(ORM):
    id: int
    number: int
    name: str
    is_installed: bool
    state: str
    relay_state: str
    load_state: str
    nominal_voltage: float
    uv_threshold: float
    ov_threshold: float
    oc_threshold: float
    state_updated_at: datetime | None
    simulated: bool = False


class ThresholdsIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    nominal_voltage: float = Field(gt=0, le=6)
    uv_threshold: float = Field(gt=0, le=6)
    ov_threshold: float = Field(gt=0, le=6)
    oc_threshold: float = Field(gt=0, le=5)

    @model_validator(mode="after")
    def _ordered(self):
        if not self.uv_threshold < self.nominal_voltage < self.ov_threshold:
            raise ValueError("thresholds must satisfy under-voltage < nominal < over-voltage")
        return self


# ---------------- telemetry (device -> server) ----------------
class TelemetryIn(BaseModel):
    """Validated against the physical limits of the 5 V prototype before anything is stored."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    voltage: float
    current: float
    power: float | None = None
    relay_state: RelayStateIn
    uptime_s: int | None = Field(default=None, ge=0)

    @validator("voltage")
    def _v(cls, v: float) -> float:
        if not 0 <= v <= get_settings().max_voltage:
            raise ValueError("voltage outside physical range")
        return v

    @validator("current")
    def _i(cls, i: float) -> float:
        if abs(i) > get_settings().max_abs_current:
            raise ValueError("current outside sensor range")
        return i

    @model_validator(mode="after")
    def _power_consistent(self):
        # The device sends P = V*I; a mismatch means a corrupt or spoofed frame, so reject it.
        if self.power is not None and abs(self.power - self.voltage * self.current) > max(0.05, 0.1 * abs(self.voltage * self.current)):
            raise ValueError("power does not match voltage x current")
        return self


class HeartbeatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    firmware_version: str | None = Field(default=None, max_length=32)
    wifi_rssi: int | None = Field(default=None, ge=-127, le=0)
    ip_address: str | None = Field(default=None, max_length=45)
    uptime_s: int | None = Field(default=None, ge=0)


# ---------------- commands ----------------
class CommandIn(BaseModel):
    """No `source` field exists: the server always records OPERATOR. ML output cannot create commands."""

    model_config = ConfigDict(extra="forbid")
    feeder_id: int
    action: Literal["TRIP", "RESTORE"]


class CommandOut(ORM):
    id: int
    feeder_id: int
    action: str
    source: str
    requested_by_name: str | None = None
    status: str
    reason: str | None
    created_at: datetime
    sent_at: datetime | None
    acked_at: datetime | None
    reported_relay_state: str | None
    is_simulated: bool


class CommandAckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    relay_state: RelayStateIn
    error: str | None = Field(default=None, max_length=200)


class DeviceCommandOut(BaseModel):
    id: int
    action: Literal["TRIP", "RESTORE"]


# ---------------- faults / notifications ----------------
class FaultOut(ORM):
    id: int
    feeder_id: int
    ts: datetime
    type: str
    severity: str
    voltage: float | None
    current: float | None
    source: str
    status: str
    cleared_at: datetime | None
    is_simulated: bool


class FaultPage(BaseModel):
    total: int
    items: list[FaultOut]


class NotificationOut(ORM):
    id: int
    feeder_id: int | None
    kind: str
    severity: str
    title: str
    message: str
    created_at: datetime
    read_at: datetime | None


# ---------------- AI ----------------
class PredictIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    voltage: float = Field(ge=0, le=6)
    current: float = Field(ge=-5, le=5)
    power: float | None = None


class PredictionOut(ORM):
    feeder_id: int | None = None
    ts: datetime | None = None
    predicted_class: str
    confidence: float
    severity: str
    model_version: str
    voltage: float
    current: float
    power: float
    is_synthetic_model: bool = True
    advisory_only: bool = True


# ---------------- devices / settings ----------------
class DeviceOut(ORM):
    id: int
    feeder_id: int
    name: str
    hw_model: str
    firmware_version: str | None
    last_heartbeat_at: datetime | None
    ip_address: str | None
    wifi_rssi: int | None
    status: str
    created_at: datetime


class DeviceCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feeder_id: int
    name: str = Field(min_length=1, max_length=80)


class DeviceCreatedOut(DeviceOut):
    api_key: str  # shown exactly once


class SettingsOut(BaseModel):
    demo_mode: bool
    heartbeat_timeout_s: int
    command_timeout_s: int


class ScenarioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feeder_id: int
    scenario: Literal["UNDERVOLTAGE", "OVERVOLTAGE", "OVERCURRENT", "ABNORMAL"] | None
    seconds: int = Field(default=15, ge=1, le=120)


class DropAckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class PushbuttonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feeder_id: int


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demo_mode: bool


# ---------------- readings ----------------
class ReadingOut(ORM):
    ts: datetime
    voltage: float
    current: float
    power: float
    relay_state: str
    is_simulated: bool


# ---------------- device events ----------------
class DeviceEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["BOOT", "PUSHBUTTON_TRIP", "PUSHBUTTON_RESTORE"]
    relay_state: RelayStateIn