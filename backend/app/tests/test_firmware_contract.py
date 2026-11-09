"""Guards the ESP32 <-> API contract without hardware: the JSON the firmware formats is extracted
from grid_monitoring.ino itself and sent to the real endpoints, so a drift in either side fails here."""
import re
from pathlib import Path

import pytest

INO = Path(__file__).resolve().parents[3] / "firmware" / "grid_monitoring" / "grid_monitoring.ino"
SRC = INO.read_text(encoding="utf8")


def c_format(fragment: str, *args):
    """Finds the snprintf JSON template containing `fragment`, then renders it like C would."""
    for lit in re.findall(r'"(\{(?:[^"\\]|\\.)*\})"', SRC):
        tmpl = lit.replace('\\"', '"')
        if fragment in tmpl:
            return tmpl.replace("%lu", "%d").replace("%%", "%") % args
    raise AssertionError(f"template with {fragment!r} not found in firmware")


def test_firmware_uses_the_documented_pin_map():
    for name, gpio in {"PIN_V": 34, "PIN_I": 35, "PIN_RELAY": 25, "PIN_BTN": 26, "PIN_RED": 32}.items():
        assert re.search(rf"#define\s+{name}\s+{gpio}\b", SRC), f"{name} must be GPIO{gpio} (report Table 4.2)"
    assert "LiquidCrystal_I2C lcd(0x27, 16, 2)" in SRC and "Wire.begin(21, 22)" in SRC


def test_relay_is_driven_active_low_and_starts_energised():
    assert "digitalWrite(PIN_RELAY, energised ? LOW : HIGH)" in SRC
    assert re.search(r"digitalWrite\(PIN_RELAY, LOW\);\s*// start NORMAL", SRC)


def test_firmware_json_is_accepted_by_the_api(client, dev_h, op_h):
    relay_words = set(re.findall(r'return energised \? "(\w+)" : "(\w+)"', SRC)[0])
    assert relay_words == {"ENERGISED", "RELEASED"}

    body = c_format('"voltage"', 5.012, 0.4213, 5.012 * 0.4213, "ENERGISED", 42)
    r = client.post("/api/device/telemetry", headers={**dev_h, "Content-Type": "application/json"}, content=body)
    assert r.status_code == 202, r.text

    hb = c_format('"firmware_version"', "1.0.0", -61, "192.168.1.77", 42)
    r = client.post("/api/device/heartbeat", headers={**dev_h, "Content-Type": "application/json"}, content=hb)
    assert r.status_code == 202, r.text
    d = client.get("/api/devices", headers=op_h).json()[0]
    assert d["firmware_version"] == "1.0.0" and d["wifi_rssi"] == -61 and d["ip_address"] == "192.168.1.77"

    for etype in ("BOOT", "PUSHBUTTON_TRIP", "PUSHBUTTON_RESTORE"):
        assert etype in SRC
        ev = c_format('"type"', etype, "ENERGISED")
        r = client.post("/api/device/events", headers={**dev_h, "Content-Type": "application/json"}, content=ev)
        assert r.status_code == 202, r.text


def test_firmware_command_and_ack_round_trip(client, dev_h, op_h):
    json_h = {**dev_h, "Content-Type": "application/json"}
    # device reports energised, operator trips, firmware polls, drives the relay, then acks with what it drives
    client.post("/api/device/telemetry", headers=json_h, content=c_format('"voltage"', 5.0, 0.4, 2.0, "ENERGISED", 1))
    f1 = next(f for f in client.get("/api/feeders", headers=op_h).json() if f["number"] == 1)
    assert f1["state"] == "NORMAL"
    cid = client.post("/api/commands", headers=op_h, json={"feeder_id": f1["id"], "action": "TRIP"}).json()["id"]

    polled = client.get("/api/device/commands/next", headers=dev_h)
    assert polled.status_code == 200 and polled.json() == {"id": cid, "action": "TRIP"}   # keys the firmware parses
    assert 'doc["action"]' in SRC and 'doc["id"]' in SRC

    path = "/api/device/commands/%d/ack" % cid
    assert "/api/device/commands/%lu/ack" in SRC
    ack = client.post(path, headers=json_h, content=c_format('"success"', "true", "RELEASED"))
    assert ack.status_code == 200 and ack.json()["status"] == "ACKED"
    assert next(f for f in client.get("/api/feeders", headers=op_h).json() if f["number"] == 1)["state"] == "TRIPPED"

    # bring the feeder back to NORMAL via the firmware's pushbutton event so later tests start clean
    client.post("/api/device/events", headers=json_h, content=c_format('"type"', "PUSHBUTTON_RESTORE", "ENERGISED"))
    client.post("/api/device/telemetry", headers=json_h, content=c_format('"voltage"', 5.0, 0.4, 2.0, "ENERGISED", 2))


def test_secrets_are_not_in_the_sketch():
    assert "config.h" in (INO.parent.parent / ".gitignore").read_text()
    assert not re.search(r"gmk_[A-Za-z0-9_\-]{20,}", SRC) and "setInsecure" not in SRC
