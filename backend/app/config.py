from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env next to the backend folder so it works whatever the working directory is (VS Code, tests, scripts).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Required: no default, so the server refuses to start without a real secret.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    database_url: str = "sqlite:///./grid_monitor.db"
    cors_origins: str = "http://localhost:5173"

    heartbeat_timeout_s: int = 15
    command_timeout_s: int = 10
    enable_background_tasks: bool = True

    # Physical limits used to validate telemetry (5 V DC prototype, ACS712-5A)
    max_voltage: float = 6.0
    max_abs_current: float = 5.0

    login_max_failures: int = 5
    login_lockout_s: int = 900

    seed_admin_operator_id: str = ""
    seed_admin_password: str = ""
    seed_admin_name: str = "Administrator"
    seed_admin_email: str = ""

    # --- Twilio SMS (all optional; SMS stays off until configured AND switched on by an admin) ---
    twilio_account_sid: str = ""
    twilio_auth_token: SecretStr = SecretStr("")
    twilio_from_number: str = ""  # E.164 sender number you own in Twilio ...
    twilio_messaging_service_sid: str = ""  # ... or a Messaging Service SID (MG...), which takes precedence
    sms_system_name: str = "GRID MONITOR"
    sms_timezone: str = "UTC"  # IANA name for timestamps in messages, e.g. Asia/Kolkata
    sms_repeat_interval_s: int = 900  # same fault/offline/boot event at most once per window
    sms_state_change_interval_s: int = 60  # trips and restores use a short window so none is missed
    sms_max_age_s: int = 900  # queued alerts older than this are dropped, not sent late

    ml_model_path: str = "../ml/models/fault_classifier.joblib"
    ml_metrics_path: str = "../ml/models/metrics.json"

    @property
    def sms_configured(self) -> bool:
        sid_ok = self.twilio_account_sid.startswith("AC") and len(self.twilio_account_sid) >= 10
        sender_ok = bool(self.twilio_from_number) or self.twilio_messaging_service_sid.startswith("MG")
        return sid_ok and bool(self.twilio_auth_token.get_secret_value()) and sender_ok

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
