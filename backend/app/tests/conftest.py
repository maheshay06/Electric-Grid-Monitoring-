import os
import tempfile

# Must be set before the app is imported. Values are test-only.
_tmp = tempfile.mkdtemp()
os.environ.update(
    JWT_SECRET="test-secret-test-secret-test-secret-0123456789",
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    ENABLE_BACKGROUND_TASKS="false",
    SEED_ADMIN_OPERATOR_ID="admin_test",
    SEED_ADMIN_PASSWORD="Test-Pass-1234",
    ML_MODEL_PATH=f"{_tmp}/no_model.joblib",
    ML_METRICS_PATH=f"{_tmp}/no_metrics.json",
    # fake Twilio credentials: tests replace the HTTP transport, nothing is ever sent
    TWILIO_ACCOUNT_SID="AC" + "0" * 32,
    TWILIO_AUTH_TOKEN="test-token-not-real",
    TWILIO_FROM_NUMBER="+15005550006",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402
from app import seed_data  # noqa: E402

ADMIN = ("admin_test", "Test-Pass-1234", "SS-SOUTH")


@pytest.fixture(scope="session")
def seeded():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        out = seed_data.run(db)
        loc = db.query(models.Location).filter_by(code="SS-SOUTH").one()
        for oid, role in (("op_test", "operator"), ("view_test", "viewer")):
            db.add(models.User(operator_id=oid, full_name=oid, role=role, location_id=loc.id,
                               password_hash=hash_password("Test-Pass-1234")))
        db.commit()
    return out["device_key"]


@pytest.fixture(scope="session")
def client(seeded):
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def device_key(seeded):
    return seeded


def login(client, operator_id, password="Test-Pass-1234", location="SS-SOUTH"):
    return client.post("/api/auth/login", json={"operator_id": operator_id, "password": password, "location_id": location})


def auth(client, operator_id):
    r = login(client, operator_id)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin_h(client):
    return auth(client, "admin_test")


@pytest.fixture(scope="session")
def op_h(client):
    return auth(client, "op_test")


@pytest.fixture(scope="session")
def viewer_h(client):
    return auth(client, "view_test")


@pytest.fixture()
def dev_h(device_key):
    return {"X-Device-Key": device_key}


def send_telemetry(client, dev_h, v=5.0, i=0.4, relay="ENERGISED"):
    return client.post("/api/device/telemetry", headers=dev_h, json={"voltage": v, "current": i, "relay_state": relay})
