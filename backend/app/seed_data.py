"""Idempotent first-run data: South Substation, Feeders 1-3 (only Feeder 1 has hardware), Feeder 1's ESP32
and one admin user taken from environment variables. No credentials are hard-coded."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Device, Feeder, Location, User
from .security import generate_device_key, hash_device_key, hash_password, password_problem


def run(db: Session) -> dict:
    s = get_settings()
    result: dict = {"device_key": None, "admin_created": False}

    loc = db.scalars(select(Location).where(Location.code == "SS-SOUTH")).first()
    if not loc:
        loc = Location(code="SS-SOUTH", name="South Substation")
        db.add(loc)
        db.flush()

    for n in (1, 2, 3):
        f = db.scalars(select(Feeder).where(Feeder.location_id == loc.id, Feeder.number == n)).first()
        if not f:
            f = Feeder(
                location_id=loc.id, number=n, name=f"Feeder {n}", is_installed=(n == 1),
                state="OFFLINE" if n == 1 else "NOT_INSTALLED",
            )
            db.add(f)
            db.flush()
        if n == 1 and f.device is None:
            key = generate_device_key()
            db.add(Device(feeder_id=f.id, name="ESP32 DevKit V1 (Feeder 1)", api_key_hash=hash_device_key(key)))
            result["device_key"] = key

    if s.seed_admin_operator_id and s.seed_admin_password:
        problem = password_problem(s.seed_admin_password, s.seed_admin_operator_id)
        if problem:
            raise SystemExit(f"SEED_ADMIN_PASSWORD rejected: {problem}.")
        if not db.scalars(select(User).where(User.operator_id == s.seed_admin_operator_id)).first():
            db.add(User(
                operator_id=s.seed_admin_operator_id, email=s.seed_admin_email or None, full_name=s.seed_admin_name,
                password_hash=hash_password(s.seed_admin_password), role="admin", location_id=loc.id,
            ))
            result["admin_created"] = True
    db.commit()
    return result
