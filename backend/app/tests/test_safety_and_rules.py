import inspect
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Device, RelayCommand
from app.routers import ai as ai_router
from app.services import heartbeat_monitor

from .conftest import send_telemetry


def test_ml_has_no_path_to_hardware(client, op_h):
    # 1. commands cannot carry a source, so "ML" cannot be requested
    r = client.post("/api/commands", headers=op_h, json={"feeder_id": 1, "action": "TRIP", "source": "ML"})
    assert r.status_code == 422
    # 2. the AI router does not even import the command service
    assert not hasattr(ai_router, "command_service")
    assert "RelayCommand" not in vars(ai_router) and "RelayCommand" not in inspect.getsource(ai_router)
    # 3. predictions are rejected honestly when no model is trained
    assert client.post("/api/ai/predict", headers=op_h, json={"voltage": 5, "current": 0.4}).status_code == 503
    assert client.get("/api/ai/metrics", headers=op_h).json()["available"] is False


def test_rule_engine_raises_events_but_never_trips(client, dev_h, op_h):
    with SessionLocal() as db:
        before = db.query(RelayCommand).count()
    send_telemetry(client, dev_h, v=5.0, relay="ENERGISED")
    send_telemetry(client, dev_h, v=5.9, relay="ENERGISED")          # first violation: not yet a fault (spike filter)
    types = [e["type"] for e in client.get("/api/faults", headers=op_h).json()["items"]]
    assert "OVERVOLTAGE" not in types
    send_telemetry(client, dev_h, v=5.9, relay="ENERGISED")          # second consecutive: fault opens
    items = client.get("/api/faults", headers=op_h).json()["items"]
    ov = next(e for e in items if e["type"] == "OVERVOLTAGE")
    assert ov["status"] == "ACTIVE"
    notes = client.get("/api/notifications", headers=op_h).json()
    assert any("OVERVOLTAGE" in n["title"] for n in notes)
    with SessionLocal() as db:
        assert db.query(RelayCommand).count() == before              # no automatic trip
    send_telemetry(client, dev_h, v=5.0, relay="ENERGISED")
    send_telemetry(client, dev_h, v=5.0, relay="ENERGISED")
    ov2 = next(e for e in client.get("/api/faults", headers=op_h).json()["items"] if e["id"] == ov["id"])
    assert ov2["status"] == "CLEARED"


def test_silent_device_goes_offline_and_alerts(client, dev_h, op_h):
    send_telemetry(client, dev_h)
    with SessionLocal() as db:
        d = db.query(Device).first()
        d.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=300)
        db.commit()
        assert heartbeat_monitor.sweep_devices(db) == 1
    f1 = next(f for f in client.get("/api/feeders", headers=op_h).json() if f["number"] == 1)
    assert f1["state"] == "OFFLINE" and f1["relay_state"] == "UNKNOWN"
    assert any(e["type"] == "DEVICE_OFFLINE" for e in client.get("/api/faults", headers=op_h).json()["items"])
    # commands to an offline device are refused
    assert client.post("/api/commands", headers=op_h, json={"feeder_id": f1["id"], "action": "TRIP"}).status_code == 409
    # and it recovers when telemetry resumes
    send_telemetry(client, dev_h)
    assert client.get("/api/devices", headers=op_h).json()[0]["status"] == "ONLINE"


def test_demo_mode_requires_admin(client, admin_h, op_h):
    assert client.put("/api/settings", headers=op_h, json={"demo_mode": True}).status_code == 403


def test_threshold_validation(client, admin_h, op_h):
    body = {"nominal_voltage": 5.0, "uv_threshold": 5.2, "ov_threshold": 5.5, "oc_threshold": 1.5}
    assert client.put("/api/feeders/1/thresholds", headers=admin_h, json=body).status_code == 422
    body["uv_threshold"] = 4.5
    assert client.put("/api/feeders/1/thresholds", headers=op_h, json=body).status_code == 403
    assert client.put("/api/feeders/1/thresholds", headers=admin_h, json=body).status_code == 200
