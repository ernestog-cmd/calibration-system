from datetime import datetime, timedelta, timezone

import jwt

from app.models import User
from app.security import ALGORITHM, SECRET_KEY
from tests.helpers import login


def test_login_returns_a_bearer_token(client, users):
    response = login(client, "admin1")
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_wrong_password_is_rejected(client, users):
    response = login(client, "admin1", "WrongPassword1")
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


def test_unknown_user_gets_the_same_message(client, users):
    response = login(client, "ghost")
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"


def test_inactive_user_cannot_log_in(client, users, db):
    db.get(User, "tech1").is_active = False
    db.commit()
    assert login(client, "tech1").status_code == 401


def test_me_requires_a_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_returns_the_user_without_secrets(client, admin_h):
    response = client.get("/auth/me", headers=admin_h)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin1"
    assert body["role"] == "admin"
    assert "hashed_password" not in body
    assert "password" not in body


def test_garbage_token_is_rejected(client, users):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not.a.token"})
    assert response.status_code == 401


def test_token_signed_with_another_key_is_rejected(client, users):
    forged = jwt.encode(
        {
            "sub": "admin1",
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "another-secret-key-that-is-long-enough-123456",
        algorithm=ALGORITHM,
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_expired_token_is_rejected(client, users):
    expired = jwt.encode(
        {
            "sub": "admin1",
            "role": "admin",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_token_of_a_deactivated_user_stops_working(client, users, tech_h, db):
    assert client.get("/auth/me", headers=tech_h).status_code == 200

    db.get(User, "tech1").is_active = False
    db.commit()

    assert client.get("/auth/me", headers=tech_h).status_code == 401


def test_logins_are_written_to_the_audit_log(client, users, admin_h):
    login(client, "admin1", "WrongPassword1")
    login(client, "admin1")

    failed = client.get("/audit", params={"action": "login_failed"}, headers=admin_h)
    assert len(failed.json()) == 1
    assert failed.json()[0]["entity_id"] == "admin1"
    assert failed.json()[0]["new_value"] == {"reason": "invalid_credentials"}

    ok = client.get("/audit", params={"action": "login"}, headers=admin_h)
    assert len(ok.json()) == 1
    assert ok.json()[0]["username"] == "admin1"