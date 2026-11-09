from .conftest import ADMIN, login


def test_login_success_returns_token_and_user(client):
    r = login(client, ADMIN[0])
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["role"] == "admin"
    assert "password" not in str(body).lower()


def test_wrong_password_and_wrong_location_give_same_generic_error(client):
    a = login(client, "op_test", password="wrong-password")
    b = login(client, "op_test", location="NOPE")
    c = login(client, "does_not_exist")
    assert a.status_code == b.status_code == c.status_code == 401
    assert a.json() == b.json() == c.json()


def test_protected_endpoints_require_token(client):
    assert client.get("/api/feeders").status_code == 401
    assert client.get("/api/feeders", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_lockout_after_repeated_failures(client):
    for _ in range(5):
        assert login(client, "ghost_user", password="x").status_code == 401
    assert login(client, "ghost_user", password="x").status_code == 429


def test_password_is_hashed(client):
    from app.database import SessionLocal
    from app.models import User

    with SessionLocal() as db:
        u = db.query(User).filter_by(operator_id="admin_test").one()
        assert u.password_hash.startswith("$2") and "Test-Pass" not in u.password_hash
