from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import RelayCommand
from app.services import command_service

from .conftest import send_telemetry


def feeder1(client, h):
    return next(f for f in client.get("/api/feeders", headers=h).json() if f["number"] == 1)


def test_viewer_cannot_command(client, viewer_h):
    f = feeder1(client, viewer_h)
    assert client.post("/api/commands", headers=viewer_h, json={"feeder_id": f["id"], "action": "TRIP"}).status_code == 403


def test_trip_is_not_successful_until_device_acks(client, dev_h, op_h):
    send_telemetry(client, dev_h, relay="ENERGISED")
    f = feeder1(client, op_h)
    assert f["state"] == "NORMAL"

    r = client.post("/api/commands", headers=op_h, json={"feeder_id": f["id"], "action": "TRIP"})
    assert r.status_code == 202 and r.json()["status"] == "PENDING"
    cmd_id = r.json()["id"]
    assert feeder1(client, op_h)["state"] == "NORMAL"            # creating a command changes nothing

    # a second command while one is in flight is refused
    assert client.post("/api/commands", headers=op_h, json={"feeder_id": f["id"], "action": "TRIP"}).status_code == 409

    nxt = client.get("/api/device/commands/next", headers=dev_h)
    assert nxt.status_code == 200 and nxt.json() == {"id": cmd_id, "action": "TRIP"}
    assert client.get(f"/api/commands/{cmd_id}", headers=op_h).json()["status"] == "SENT"
    assert feeder1(client, op_h)["state"] == "NORMAL"            # still nothing: no ack yet
    assert client.get("/api/device/commands/next", headers=dev_h).status_code == 204

    ack = client.post(f"/api/device/commands/{cmd_id}/ack", headers=dev_h,
                      json={"success": True, "relay_state": "RELEASED"})
    assert ack.status_code == 200 and ack.json()["status"] == "ACKED"
    after = feeder1(client, op_h)
    assert after["state"] == "TRIPPED" and after["relay_state"] == "RELEASED"


def test_ack_with_mismatched_relay_state_is_failure_not_success(client, dev_h, op_h):
    send_telemetry(client, dev_h, relay="RELEASED")                 # currently tripped from previous test
    f = feeder1(client, op_h)
    cmd = client.post("/api/commands", headers=op_h, json={"feeder_id": f["id"], "action": "RESTORE"}).json()
    client.get("/api/device/commands/next", headers=dev_h)
    r = client.post(f"/api/device/commands/{cmd['id']}/ack", headers=dev_h,
                    json={"success": True, "relay_state": "RELEASED"})  # claims success but relay did NOT energise
    assert r.json()["status"] == "FAILED"
    assert feeder1(client, op_h)["state"] == "TRIPPED"


def test_unacknowledged_command_times_out_without_changing_state(client, dev_h, op_h):
    send_telemetry(client, dev_h, relay="RELEASED")
    f = feeder1(client, op_h)
    cmd = client.post("/api/commands", headers=op_h, json={"feeder_id": f["id"], "action": "RESTORE"}).json()
    with SessionLocal() as db:
        c = db.get(RelayCommand, cmd["id"])
        c.created_at = datetime.now(timezone.utc) - timedelta(seconds=120)
        db.commit()
        assert command_service.expire_stale(db) == 1
    assert client.get(f"/api/commands/{cmd['id']}", headers=op_h).json()["status"] == "TIMEOUT"
    assert feeder1(client, op_h)["state"] == "TRIPPED"


def test_device_cannot_ack_someone_elses_or_unsent_command(client, dev_h):
    assert client.post("/api/device/commands/99999/ack", headers=dev_h,
                       json={"success": True, "relay_state": "RELEASED"}).status_code == 404


def test_pushbutton_event_updates_state_and_logs(client, dev_h, op_h):
    r = client.post("/api/device/events", headers=dev_h, json={"type": "PUSHBUTTON_RESTORE", "relay_state": "ENERGISED"})
    assert r.status_code == 202
    assert feeder1(client, op_h)["state"] == "NORMAL"
    sources = {e["source"] for e in client.get("/api/faults", headers=op_h).json()["items"]}
    assert "PUSHBUTTON" in sources
