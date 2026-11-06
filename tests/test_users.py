import pytest

from tests.helpers import PASSWORD, login

NEW_USER = {
    "username": "newtech",
    "password": "Secret123",
    "first_name": "New",
    "last_name": "Tech",
    "role": "technician",
}


def test_admin_creates_a_user(client, admin_h):
    response = client.post("/users", json=NEW_USER, headers=admin_h)
    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "newtech"
    assert body["role"] == "technician"
    assert body["is_active"] is True
    assert "password" not in body
    assert "hashed_password" not in body


def test_duplicate_username_is_a_conflict(client, admin_h):
    response = client.post("/users", json={**NEW_USER, "username": "tech1"}, headers=admin_h)
    assert response.status_code == 409


def test_only_admins_can_manage_users(client, tech_h, auditor_h):
    assert client.post("/users", json=NEW_USER, headers=tech_h).status_code == 403
    assert client.get("/users", headers=tech_h).status_code == 403
    assert client.get("/users", headers=auditor_h).status_code == 403
    assert client.get("/users").status_code == 401


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short"},
        {"password": "a" * 73},
        {"username": "bad user"},
        {"username": "ab"},
        {"role": "boss"},
    ],
)
def test_invalid_users_are_rejected(client, admin_h, overrides):
    response = client.post("/users", json={**NEW_USER, **overrides}, headers=admin_h)
    assert response.status_code == 422


def test_admin_lists_users(client, admin_h):
    response = client.get("/users", headers=admin_h)
    assert response.status_code == 200
    assert [u["username"] for u in response.json()] == ["admin1", "auditor1", "tech1"]


def test_unknown_user_is_not_found(client, admin_h):
    assert client.get("/users/ghost", headers=admin_h).status_code == 404
    response = client.patch("/users/ghost", json={"first_name": "X"}, headers=admin_h)
    assert response.status_code == 404


def test_patch_changes_the_role(client, admin_h):
    response = client.patch("/users/tech1", json={"role": "auditor"}, headers=admin_h)
    assert response.status_code == 200
    assert response.json()["role"] == "auditor"


def test_password_change_replaces_the_old_password(client, admin_h):
    response = client.patch(
        "/users/tech1", json={"password": "NewSecret456"}, headers=admin_h
    )
    assert response.status_code == 200
    assert login(client, "tech1", "NewSecret456").status_code == 200
    assert login(client, "tech1", PASSWORD).status_code == 401


def test_deactivated_user_cannot_log_in(client, admin_h):
    response = client.patch("/users/tech1", json={"is_active": False}, headers=admin_h)
    assert response.status_code == 200
    assert login(client, "tech1").status_code == 401


@pytest.mark.parametrize("changes", [{"is_active": False}, {"role": "technician"}])
def test_admin_cannot_lock_themselves_out(client, admin_h, changes):
    response = client.patch("/users/admin1", json=changes, headers=admin_h)
    assert response.status_code == 400