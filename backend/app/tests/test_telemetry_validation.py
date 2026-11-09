from .conftest import send_telemetry


def test_device_key_required(client):
    r = client.post("/api/device/telemetry", json={"voltage": 5, "current": 0.4, "relay_state": "ENERGISED"})
    assert r.status_code == 401
    r = client.post("/api/device/telemetry", headers={"X-Device-Key": "gmk_wrong"},
                    json={"voltage": 5, "current": 0.4, "relay_state": "ENERGISED"})
    assert r.status_code == 401


def test_physically_impossible_values_rejected(client, dev_h):
    assert send_telemetry(client, dev_h, v=9.9).status_code == 422       # above ADC-safe supply range
    assert send_telemetry(client, dev_h, v=-1).status_code == 422
    assert send_telemetry(client, dev_h, i=7).status_code == 422         # beyond ACS712-5A
    assert client.post("/api/device/telemetry", headers=dev_h,
                       json={"voltage": 5, "current": 0.4, "power": 50, "relay_state": "ENERGISED"}).status_code == 422
    assert client.post("/api/device/telemetry", headers=dev_h,
                       json={"voltage": 5, "current": 0.4, "relay_state": "ENERGISED", "extra": 1}).status_code == 422
    assert client.post("/api/device/telemetry", headers=dev_h,
                       json={"voltage": 5, "current": 0.4, "relay_state": "MAYBE"}).status_code == 422


def test_valid_telemetry_is_stored_and_marks_device_online(client, dev_h, admin_h):
    assert send_telemetry(client, dev_h).status_code == 202
    feeders = client.get("/api/feeders", headers=admin_h).json()
    f1 = next(f for f in feeders if f["number"] == 1)
    assert f1["state"] == "NORMAL" and f1["relay_state"] == "ENERGISED"
    assert client.get("/api/devices", headers=admin_h).json()[0]["status"] == "ONLINE"
    rows = client.get("/api/readings", params={"feeder_id": f1["id"], "range": "1m"}, headers=admin_h).json()
    assert rows and rows[-1]["is_simulated"] is False
