"""Admin user management, self-service password change, token invalidation and the SQLite upgrade helper."""
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect

from app.database import SessionLocal
from app.models import AuditLog
from app.migrate import add_missing_columns

from .conftest import ADMIN, auth, login

PW = "Fresh-Pass-2026"


def new_user(client, admin_h, oid, role="operator", pw=PW, **extra):
    body = {"operator_id": oid, "full_name": f"User {oid}", "role": role, "location_code": "SS-SOUTH", "password": pw, **extra}
    return client.post("/api/users", headers=admin_h, json=body)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_only_admin_can_manage_users(client, op_h, viewer_h):
    for h in (op_h, viewer_h):
        assert client.get("/api/users", headers=h).status_code == 403
        assert client.post("/api/users", headers=h, json={}).status_code == 403
        assert client.patch("/api/users/1", headers=h, json={"role": "admin"}).status_code == 403
        assert client.post("/api/users/1/reset-password", headers=h, json={"new_password": PW}).status_code == 403
    assert client.get("/api/users").status_code == 401


def test_create_list_and_login_as_new_user(client, admin_h):
    r = new_user(client, admin_h, "um_alice", email="Alice@Example.com")
    assert r.status_code == 201
    u = r.json()
    assert u["email"] == "alice@example.com" and u["role"] == "operator" and u["location_code"] == "SS-SOUTH"
    assert "password" not in str(u).lower()
    listed = client.get("/api/users", headers=admin_h).json()
    assert any(x["operator_id"] == "um_alice" for x in listed)
    assert all("password_hash" not in x for x in listed)
    ok = login(client, "um_alice", PW)
    assert ok.status_code == 200 and ok.json()["user"]["role"] == "operator"
    with SessionLocal() as db:
        assert db.query(AuditLog).filter_by(action="USER_CREATE").count() >= 1


def test_create_validation(client, admin_h):
    assert new_user(client, admin_h, "um_alice").status_code == 409                 # duplicate
    assert new_user(client, admin_h, "UM_ALICE").status_code == 409                 # case-insensitive duplicate
    assert new_user(client, admin_h, "um_dup", email="alice@example.com").status_code == 409
    assert new_user(client, admin_h, "x").status_code == 422                        # too short
    assert new_user(client, admin_h, "bad id!").status_code == 422
    assert new_user(client, admin_h, "um_weak1", pw="short1").status_code == 422
    assert new_user(client, admin_h, "um_weak2", pw="onlyletterspassword").status_code == 422
    assert new_user(client, admin_h, "um_weak3", pw="1234567890123").status_code == 422
    assert new_user(client, admin_h, "um_weak4", pw="um_weak4-pass1").status_code == 422    # contains operator id
    assert new_user(client, admin_h, "um_role", role="superuser").status_code == 422
    assert new_user(client, admin_h, "um_loc", location_code="NOWHERE").status_code == 422
    assert client.post("/api/users", headers=admin_h, json={"operator_id": "um_x", "full_name": "x", "location_code": "SS-SOUTH",
                                                            "password": PW, "is_admin": True}).status_code == 422


def test_role_change_is_immediate_and_signs_user_out_everywhere(client, admin_h):
    uid = new_user(client, admin_h, "um_bob").json()["id"]
    token = login(client, "um_bob", PW).json()["access_token"]
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200
    assert client.patch(f"/api/users/{uid}", headers=admin_h, json={"role": "viewer"}).json()["role"] == "viewer"
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401          # old token dead
    viewer = login(client, "um_bob", PW).json()["access_token"]
    assert client.post("/api/commands", headers=bearer(viewer), json={"feeder_id": 1, "action": "TRIP"}).status_code == 403


def test_deactivated_user_cannot_use_tokens_or_log_in_and_can_return(client, admin_h):
    uid = new_user(client, admin_h, "um_carol").json()["id"]
    token = login(client, "um_carol", PW).json()["access_token"]
    assert client.patch(f"/api/users/{uid}", headers=admin_h, json={"is_active": False}).json()["is_active"] is False
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401
    assert login(client, "um_carol", PW).status_code == 401
    client.patch(f"/api/users/{uid}", headers=admin_h, json={"is_active": True})
    assert login(client, "um_carol", PW).status_code == 200


def test_admin_cannot_demote_or_deactivate_self(client, admin_h):
    me = next(u for u in client.get("/api/users", headers=admin_h).json() if u["operator_id"] == ADMIN[0])
    assert client.patch(f"/api/users/{me['id']}", headers=admin_h, json={"role": "operator"}).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", headers=admin_h, json={"is_active": False}).status_code == 409
    assert client.patch(f"/api/users/{me['id']}", headers=admin_h, json={"full_name": "Renamed Admin"}).status_code == 200
    assert client.patch("/api/users/99999", headers=admin_h, json={"role": "viewer"}).status_code == 404
    assert client.patch(f"/api/users/{me['id']}", headers=admin_h, json={"password_hash": "x"}).status_code == 422


def test_admin_reset_password_invalidates_old_password_and_tokens(client, admin_h):
    uid = new_user(client, admin_h, "um_dave").json()["id"]
    old_token = login(client, "um_dave", PW).json()["access_token"]
    assert client.post(f"/api/users/{uid}/reset-password", headers=admin_h, json={"new_password": "weak"}).status_code == 422
    assert client.post(f"/api/users/{uid}/reset-password", headers=admin_h, json={"new_password": "Reset-Pass-4455"}).status_code == 204
    assert client.get("/api/auth/me", headers=bearer(old_token)).status_code == 401
    assert login(client, "um_dave", PW).status_code == 401
    assert login(client, "um_dave", "Reset-Pass-4455").status_code == 200


def test_change_own_password(client, admin_h):
    new_user(client, admin_h, "um_erin")
    tok = login(client, "um_erin", PW).json()["access_token"]
    other = login(client, "um_erin", PW).json()["access_token"]
    h = bearer(tok)
    url = "/api/auth/change-password"
    wrong = client.post(url, headers=h, json={"current_password": "nope-nope-123", "new_password": "Another-Pass-77"})
    assert wrong.status_code == 400                                   # 400, not 401: must not sign the user out in the UI
    assert client.post(url, headers=h, json={"current_password": PW, "new_password": "weak"}).status_code == 422
    assert client.post(url, headers=h, json={"current_password": PW, "new_password": PW}).status_code == 422
    r = client.post(url, headers=h, json={"current_password": PW, "new_password": "Another-Pass-77"})
    assert r.status_code == 200
    fresh = r.json()["access_token"]
    assert client.get("/api/auth/me", headers=bearer(fresh)).status_code == 200      # this session continues
    assert client.get("/api/auth/me", headers=h).status_code == 401                  # old token revoked
    assert client.get("/api/auth/me", headers=bearer(other)).status_code == 401      # so is the user's other session
    assert login(client, "um_erin", PW).status_code == 401
    assert login(client, "um_erin", "Another-Pass-77").status_code == 200


def test_change_password_attempts_are_throttled(client, admin_h):
    new_user(client, admin_h, "um_frank")
    h = bearer(login(client, "um_frank", PW).json()["access_token"])
    for _ in range(5):
        assert client.post("/api/auth/change-password", headers=h, json={"current_password": "wrong-wrong-1", "new_password": "Brand-New-Pass-9"}).status_code == 400
    assert client.post("/api/auth/change-password", headers=h, json={"current_password": PW, "new_password": "Brand-New-Pass-9"}).status_code == 429


def test_actions_are_audited_without_secrets(client, admin_h):
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(AuditLog.action.like("USER_%") | (AuditLog.action == "PASSWORD_CHANGE")).all()
        assert {r.action for r in rows} >= {"USER_CREATE", "USER_UPDATE", "USER_PASSWORD_RESET", "PASSWORD_CHANGE"}
        assert not any(PW in r.detail or "Reset-Pass" in r.detail or "Another-Pass" in r.detail for r in rows)


def test_locations_listing(client, admin_h):
    assert {"code": "SS-SOUTH", "name": "South Substation"} in client.get("/api/users/locations", headers=admin_h).json()


# ---------------- upgrading databases created by an older version ----------------
def test_migration_adds_missing_columns_and_keeps_rows(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(
        """
        CREATE TABLE locations (id INTEGER PRIMARY KEY, code VARCHAR(32) UNIQUE, name VARCHAR(120));
        CREATE TABLE users (id INTEGER PRIMARY KEY, operator_id VARCHAR(64) UNIQUE, email VARCHAR(160), full_name VARCHAR(120) NOT NULL,
            password_hash VARCHAR(255) NOT NULL, role VARCHAR(16) NOT NULL, location_id INTEGER NOT NULL, is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL, last_login_at DATETIME);
        INSERT INTO locations VALUES (1, 'SS-SOUTH', 'South Substation');
        INSERT INTO users VALUES (1, 'old_admin', NULL, 'Old Admin', 'hash', 'admin', 1, 1, '2026-01-01 00:00:00', NULL);
        """
    )
    con.commit()
    con.close()
    engine = create_engine(f"sqlite:///{db}")
    added = add_missing_columns(engine)
    assert "users.token_version" in added
    assert "token_version" in {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.connect() as c:
        row = c.exec_driver_sql("SELECT operator_id, token_version FROM users").one()
    assert tuple(row) == ("old_admin", 0)                      # data kept, NOT NULL column got its default
    assert add_missing_columns(engine) == []                   # idempotent
