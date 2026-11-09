"""Run once after configuring .env:   python seed.py"""
from app import models  # noqa: F401
from app.database import Base, SessionLocal, engine
from app.migrate import add_missing_columns
from app.seed_data import run

Base.metadata.create_all(engine)
add_missing_columns(engine)
with SessionLocal() as db:
    out = run(db)

print("Seed complete.")
print("  Admin user created:", out["admin_created"] or "no (already exists, or SEED_ADMIN_* not set)")
if out["device_key"]:
    print("\n  ESP32 device API key for Feeder 1 (shown ONCE - put it in firmware config.h):")
    print(" ", out["device_key"])
else:
    print("  Device already registered; rotate its key from Device Management if you lost it.")
