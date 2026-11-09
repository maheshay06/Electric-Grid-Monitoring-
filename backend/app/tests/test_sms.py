"""Twilio SMS: outbox, templates, rate limiting, failure handling. Twilio itself is replaced by a mock transport,
so no real message is ever sent and no network is used."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.database import SessionLocal
from app.models import Device, Feeder, SmsMessage, SmsRecipient
from app.services import demo_simulator, heartbeat_monitor, sms_service, sms_worker, twilio_client

from .conftest import send_telemetry

NUMBERS = ["+15558675301", "+15558675302"]  # fictitious test numbers
SECRET = "test-token-not-real"


class FakeTwilio:
    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.responder = lambda req: httpx.Response(201, json={"sid": "SM" + "a" * 32, "status": "queued"})

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.responder(request)

    def form(self, i=-1):
        return {k: v[0] for k, v in parse_qs(self.calls[i].content.decode()).items()}


@pytest.fixture()
def twilio():
    fake = FakeTwilio()
    twilio_client.set_transport(httpx.MockTransport(fake))
    yield fake
    twilio_client.set_transport(None)


@pytest.fixture()
def sms_on(client, admin_h, twilio):
    for n in NUMBERS:
        assert client.post("/api/sms/recipients", headers=admin_h, json={"phone": n, "label": "t"}).status_code == 201
    assert client.put("/api/sms/enabled", headers=admin_h, json={"enabled": True}).json()["enabled"] is True
    yield twilio
    client.put("/api/sms/enabled", headers=admin_h, json={"enabled": False})
    with SessionLocal() as db:
        db.query(SmsMessage).delete()
        db.query(SmsRecipient).delete()
        db.commit()


def outbox(status=None, kind=None):
    with SessionLocal() as db:
        q = db.query(SmsMessage)
        if status:
            q = q.filter(SmsMessage.status == status)
        if kind:
            q = q.filter(SmsMessage.kind == kind)
        return q.order_by(SmsMessage.id).all()


def work():
    with SessionLocal() as db:
        return sms_worker.process_queue(db)


def healthy(client, dev_h):
    for _ in range(2):
        send_telemetry(client, dev_h, 5.0, 0.4, "ENERGISED")


def test_off_by_default_and_admin_only_controls(client, admin_h, op_h, viewer_h):
    st = client.get("/api/sms/status", headers=viewer_h).json()
    assert st["configured"] is True and st["enabled"] is False and st["demo_mode_never_sends"] is True
    assert client.get("/api/sms/recipients", headers=op_h).status_code == 403
    assert client.post("/api/sms/recipients", headers=op_h, json={"phone": NUMBERS[0]}).status_code == 403
    assert client.put("/api/sms/enabled", headers=op_h, json={"enabled": True}).status_code == 403
    assert client.post("/api/sms/test", headers=op_h, json={"recipient_id": 1}).status_code == 403
    assert SECRET not in json.dumps(st)


def test_recipient_validation(client, admin_h, twilio):
    for bad in ("9876543210", "+0123456789", "+1", "abc", "+1 555 867 53 01 99999999"):
        assert client.post("/api/sms/recipients", headers=admin_h, json={"phone": bad}).status_code == 422, bad
    r = client.post("/api/sms/recipients", headers=admin_h, json={"phone": "+1 555 867 5303"})
    assert r.status_code == 201 and r.json()["phone"] == "+15558675303"       # spaces normalised
    assert client.post("/api/sms/recipients", headers=admin_h, json={"phone": "+15558675303"}).status_code == 409
    assert client.delete(f"/api/sms/recipients/{r.json()['id']}", headers=admin_h).status_code == 204


def test_cannot_enable_without_credentials(client, admin_h, monkeypatch):
    from app.config import get_settings

    unconfigured = get_settings().model_copy(update={"twilio_account_sid": ""})
    monkeypatch.setattr("app.routers.sms.get_settings", lambda: unconfigured)
    assert client.put("/api/sms/enabled", headers=admin_h, json={"enabled": True}).status_code == 409


def test_no_sms_while_alerts_are_disabled(client, dev_h, admin_h, twilio):
    client.post("/api/sms/recipients", headers=admin_h, json={"phone": NUMBERS[0]})
    try:
        send_telemetry(client, dev_h, 5.0, 0.4)
        send_telemetry(client, dev_h, 5.0, 2.2)
        send_telemetry(client, dev_h, 5.0, 2.2)
        assert outbox() == [] and work() == 0 and twilio.calls == []
    finally:
        healthy(client, dev_h)
        with SessionLocal() as db:
            db.query(SmsRecipient).delete()
            db.commit()


def test_overcurrent_sends_one_sms_per_recipient_with_correct_request(client, dev_h, sms_on):
    healthy(client, dev_h)
    send_telemetry(client, dev_h, 5.0, 2.2)
    assert outbox() == []                                       # first spike is filtered by the rule engine
    send_telemetry(client, dev_h, 5.0, 2.2)
    q = outbox("QUEUED", "OVERCURRENT")
    assert sorted(m.to_number for m in q) == NUMBERS
    assert "CURRENT ALERT" in q[0].body and "Feeder 1" in q[0].body and "I=2.20A" in q[0].body

    assert work() == 2
    assert [m.status for m in outbox(kind="OVERCURRENT")] == ["SENT", "SENT"]
    req = sms_on.calls[0]
    assert req.method == "POST" and "/Accounts/AC" in str(req.url) and str(req.url).endswith("/Messages.json")
    assert req.headers["authorization"].startswith("Basic ")
    form = sms_on.form(0)
    assert form["To"] in NUMBERS and form["From"] == "+15005550006" and "OVERCURRENT" in form["Body"]
    healthy(client, dev_h)


def test_repeat_of_same_event_inside_interval_is_suppressed(client, dev_h, sms_on):
    healthy(client, dev_h)
    for _ in range(2):
        send_telemetry(client, dev_h, 5.0, 2.2)
    work()
    healthy(client, dev_h)                                       # fault clears
    for _ in range(2):
        send_telemetry(client, dev_h, 5.0, 2.2)                  # same fault opens again, seconds later
    assert len(outbox("SENT", "OVERCURRENT")) == 2               # still only the first two messages
    skipped = outbox("SKIPPED", "OVERCURRENT")
    assert len(skipped) == 1 and "repeat suppressed" in skipped[0].error
    assert work() == 0
    healthy(client, dev_h)


def test_trip_message_says_reported_not_physically_disconnected(client, dev_h, op_h, sms_on):
    healthy(client, dev_h)
    f1 = next(f for f in client.get("/api/feeders", headers=op_h).json() if f["number"] == 1)
    cid = client.post("/api/commands", headers=op_h, json={"feeder_id": f1["id"], "action": "TRIP"}).json()["id"]
    assert outbox() == []                                        # requesting a trip texts nobody
    client.get("/api/device/commands/next", headers=dev_h)
    assert outbox() == []                                        # nor does the device merely receiving it
    client.post(f"/api/device/commands/{cid}/ack", headers=dev_h, json={"success": True, "relay_state": "RELEASED"})
    trip = outbox("QUEUED", "TRIPPED")
    assert len(trip) == 2
    body = trip[0].body.lower()
    assert "reported tripped" in body and "released" in body and "operator command" in body
    assert "has been disconnected" not in body and "physically" not in body

    # local pushbutton restore uses its own (short) window, so the trip does not suppress it
    client.post("/api/device/events", headers=dev_h, json={"type": "PUSHBUTTON_RESTORE", "relay_state": "ENERGISED"})
    assert len(outbox("QUEUED", "RESTORED")) == 2
    healthy(client, dev_h)


def test_boot_and_device_offline_alerts(client, dev_h, sms_on):
    client.post("/api/device/events", headers=dev_h, json={"type": "BOOT", "relay_state": "ENERGISED"})
    assert len(outbox("QUEUED", "BOOT")) == 2
    send_telemetry(client, dev_h)
    with SessionLocal() as db:
        db.query(Device).first().last_heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=600)
        db.commit()
        assert heartbeat_monitor.sweep_devices(db) == 1
    off = outbox("QUEUED", "DEVICE_OFFLINE")
    assert len(off) == 2 and "communication" in off[0].body.lower()
    send_telemetry(client, dev_h)
    healthy(client, dev_h)


def test_twilio_permanent_error_is_not_retried(client, dev_h, sms_on):
    sms_on.responder = lambda r: httpx.Response(400, json={"code": 21608, "message": "The number is unverified (trial account)."})
    client.post("/api/device/events", headers=dev_h, json={"type": "BOOT", "relay_state": "ENERGISED"})
    assert work() == 0
    failed = outbox("FAILED")
    assert len(failed) == 2 and failed[0].attempts == 1 and "21608" in failed[0].error
    n = len(sms_on.calls)
    assert work() == 0 and len(sms_on.calls) == n                # nothing left to retry
    assert SECRET not in failed[0].error


def test_twilio_transient_error_retries_then_fails(client, dev_h, sms_on):
    sms_on.responder = lambda r: httpx.Response(503, json={"message": "Service unavailable"})
    client.post("/api/device/events", headers=dev_h, json={"type": "BOOT", "relay_state": "ENERGISED"})
    for attempt in range(1, 4):
        work()
        rows = outbox(kind="BOOT")
        assert all(m.attempts == attempt for m in rows)
        if attempt < 3:
            assert all(m.status == "QUEUED" and m.next_attempt_at for m in rows)
            with SessionLocal() as db:                           # skip the back-off wait
                for m in db.query(SmsMessage):
                    m.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
    assert [m.status for m in outbox(kind="BOOT")] == ["FAILED", "FAILED"]


def test_stale_alert_is_dropped_not_sent_late(client, dev_h, sms_on):
    client.post("/api/device/events", headers=dev_h, json={"type": "BOOT", "relay_state": "ENERGISED"})
    with SessionLocal() as db:
        for m in db.query(SmsMessage):
            m.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
    assert work() == 0 and sms_on.calls == []
    assert {m.status for m in outbox(kind="BOOT")} == {"SKIPPED"}


def test_demo_mode_never_sends_sms(client, admin_h, op_h, sms_on):
    client.put("/api/settings", headers=admin_h, json={"demo_mode": True})
    try:
        client.post("/api/demo/scenario", headers=op_h, json={"feeder_id": 1, "scenario": "OVERCURRENT", "seconds": 30})
        with SessionLocal() as db:
            for _ in range(5):
                demo_simulator.tick(db)
        assert any(e["type"] == "OVERCURRENT" for e in client.get("/api/faults", headers=op_h).json()["items"])
        # a simulated pushbutton trip is silent too
        client.post("/api/demo/pushbutton", headers=op_h, json={"feeder_id": 2})
        assert outbox() == [] and work() == 0 and sms_on.calls == []
        with SessionLocal() as db:
            assert sms_service.enqueue(db, "TRIPPED", db.get(Feeder, 1), simulated=True) == 0
    finally:
        client.put("/api/settings", headers=admin_h, json={"demo_mode": False})


def test_test_message_goes_to_one_chosen_recipient(client, admin_h, sms_on):
    rid = client.get("/api/sms/recipients", headers=admin_h).json()[0]["id"]
    assert client.post("/api/sms/test", headers=admin_h, json={"recipient_id": rid}).json() == {"queued": 1}
    assert work() == 1
    assert "Test message" in sms_on.form(0)["Body"] and len(sms_on.calls) == 1


def test_messages_are_plain_ascii_short_and_listed_masked(client, dev_h, op_h, sms_on):
    healthy(client, dev_h)
    for _ in range(2):
        send_telemetry(client, dev_h, 4.0, 0.4)                  # undervoltage
    for _ in range(2):
        send_telemetry(client, dev_h, 5.9, 0.4)                  # overvoltage
    work()
    for m in outbox("SENT"):
        assert m.body.isascii() and len(m.body) <= 320, m.body
    rows = client.get("/api/sms/messages", headers=op_h).json()
    assert rows and all("*" in r["to"] and r["to"] not in NUMBERS for r in rows if r["to"] != "-")
    assert SECRET not in json.dumps(rows)
    healthy(client, dev_h)
