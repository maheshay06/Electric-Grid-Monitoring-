from datetime import datetime, timedelta, timezone

import pytest

from app.database import SessionLocal
from app.models import Feeder, RelayCommand
from app.services import command_service, demo_simulator

from .conftest import send_telemetry


@pytest.fixture()
def demo_on(client, admin_h):
    assert client.put("/api/settings", headers=admin_h, json={"demo_mode": True}).json()["demo_mode"] is True
    yield
    client.put("/api/settings", headers=admin_h, json={"demo_mode": False})


def tick(n=1):
    with SessionLocal() as db:
        for _ in range(n):
            assert demo_simulator.tick(db)


def backdate(cmd_id, seconds):
    with SessionLocal() as db:
        db.get(RelayCommand, cmd_id).created_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        db.commit()


def feeders(client, h):
    return {f["number"]: f for f in client.get("/api/feeders", headers=h).json()}


def test_demo_endpoints_refuse_when_demo_off(client, op_h, viewer_h):
    assert client.post("/api/demo/scenario", headers=op_h, json={"feeder_id": 1, "scenario": "OVERCURRENT"}).status_code == 409
    assert client.post("/api/demo/pushbutton", headers=op_h, json={"feeder_id": 1}).status_code == 409
    assert client.post("/api/demo/drop-ack", headers=viewer_h, json={"enabled": True}).status_code == 403


def test_demo_data_is_flagged_and_never_mixed_with_live(client, admin_h, op_h, dev_h):
    send_telemetry(client, dev_h, v=5.0, i=0.4)                     # a real reading exists
    live_n = len(client.get("/api/readings", params={"feeder_id": 1, "range": "24h"}, headers=op_h).json())
    client.put("/api/settings", headers=admin_h, json={"demo_mode": True})
    try:
        rows = client.get("/api/readings", params={"feeder_id": 1, "range": "24h"}, headers=op_h).json()
        assert rows and all(r["is_simulated"] for r in rows)
        faults = client.get("/api/faults", headers=op_h).json()["items"]
        assert faults and all(e["is_simulated"] for e in faults)
        f = feeders(client, op_h)
        assert f[2]["simulated"] and f[2]["is_installed"] and f[2]["state"] == "NORMAL"
        summary = client.get("/api/dashboard/summary", headers=op_h).json()
        assert summary["demo_mode"] and summary["esp32_online"] is False
    finally:
        client.put("/api/settings", headers=admin_h, json={"demo_mode": False})
    after = client.get("/api/readings", params={"feeder_id": 1, "range": "24h"}, headers=op_h).json()
    assert len(after) == live_n and not any(r["is_simulated"] for r in after)
    assert not any(e["is_simulated"] for e in client.get("/api/faults", headers=op_h).json()["items"])
    assert feeders(client, op_h)[2]["state"] == "NOT_INSTALLED"      # real feeder row untouched


def test_demo_command_needs_simulated_ack_and_leaves_live_state_alone(client, op_h, demo_on):
    r = client.post("/api/commands", headers=op_h, json={"feeder_id": 2, "action": "TRIP"})
    assert r.status_code == 202 and r.json()["status"] == "PENDING" and r.json()["is_simulated"] is True
    cid = r.json()["id"]
    assert feeders(client, op_h)[2]["state"] == "NORMAL"            # nothing changes at request time
    assert client.post("/api/commands", headers=op_h, json={"feeder_id": 2, "action": "TRIP"}).status_code == 409

    backdate(cid, 3)
    tick()                                                           # PENDING -> SENT
    assert client.get(f"/api/commands/{cid}", headers=op_h).json()["status"] == "SENT"
    assert feeders(client, op_h)[2]["state"] == "NORMAL"
    tick()                                                           # SENT -> ACKED (simulated ack)
    assert client.get(f"/api/commands/{cid}", headers=op_h).json()["status"] == "ACKED"
    assert feeders(client, op_h)[2]["state"] == "TRIPPED"
    with SessionLocal() as db:
        assert db.query(Feeder).filter_by(number=2).one().state == "NOT_INSTALLED"
    tick()                                                           # next sample reflects the released relay
    # tripped feeder now draws ~no current
    last = client.get("/api/readings", params={"feeder_id": 2, "range": "1m"}, headers=op_h).json()[-1]
    assert last["current"] < 0.1 and last["relay_state"] == "RELEASED"

    r = client.post("/api/commands", headers=op_h, json={"feeder_id": 2, "action": "RESTORE"})
    backdate(r.json()["id"], 3)
    tick(2)
    assert feeders(client, op_h)[2]["state"] == "NORMAL"


def test_demo_dropped_ack_times_out_and_state_is_unchanged(client, op_h, demo_on):
    assert client.post("/api/demo/drop-ack", headers=op_h, json={"enabled": True}).json()["drop_ack"] is True
    try:
        cid = client.post("/api/commands", headers=op_h, json={"feeder_id": 3, "action": "TRIP"}).json()["id"]
        backdate(cid, 3)
        tick(3)
        assert client.get(f"/api/commands/{cid}", headers=op_h).json()["status"] == "SENT"
        backdate(cid, 120)
        with SessionLocal() as db:
            assert command_service.expire_stale(db) >= 1
        assert client.get(f"/api/commands/{cid}", headers=op_h).json()["status"] == "TIMEOUT"
        assert feeders(client, op_h)[3]["state"] == "NORMAL"
    finally:
        client.post("/api/demo/drop-ack", headers=op_h, json={"enabled": False})


def test_demo_fault_scenario_raises_event_but_never_trips(client, op_h, demo_on):
    with SessionLocal() as db:
        before = db.query(RelayCommand).count()
    assert client.post("/api/demo/scenario", headers=op_h, json={"feeder_id": 1, "scenario": "OVERCURRENT", "seconds": 30}).status_code == 200
    tick(4)
    items = client.get("/api/faults", params={"feeder_id": 1, "type": "OVERCURRENT"}, headers=op_h).json()["items"]
    assert any(e["status"] == "ACTIVE" and e["is_simulated"] for e in items)
    assert feeders(client, op_h)[1]["state"] == "NORMAL"            # detection alone never trips
    with SessionLocal() as db:
        assert db.query(RelayCommand).count() == before
    assert any("OVERCURRENT" in n["title"] for n in client.get("/api/notifications", headers=op_h).json())
    client.post("/api/demo/scenario", headers=op_h, json={"feeder_id": 1, "scenario": None})
    tick(4)


def test_simulated_pushbutton_is_logged_with_source(client, op_h, demo_on):
    assert client.post("/api/demo/pushbutton", headers=op_h, json={"feeder_id": 1}).status_code == 200
    assert feeders(client, op_h)[1]["state"] == "TRIPPED"
    sources = [e["source"] for e in client.get("/api/faults", params={"feeder_id": 1}, headers=op_h).json()["items"]]
    assert "PUSHBUTTON" in sources
    client.post("/api/demo/pushbutton", headers=op_h, json={"feeder_id": 1})
    assert feeders(client, op_h)[1]["state"] == "NORMAL"
