from sqlalchemy import select

from app.models import AuditLog, User, UserRole
from app.services import bootstrap
from tests.conftest import TestingSession
from tests.helpers import login


def run_bootstrap(monkeypatch, username="boss", password="Secret1234"):
    monkeypatch.setattr(bootstrap, "SessionLocal", TestingSession)
    monkeypatch.setenv("ADMIN_USERNAME", username)
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    bootstrap.create_first_admin()


def test_first_admin_is_created_on_an_empty_system(client, db, monkeypatch):
    run_bootstrap(monkeypatch)

    admin = db.get(User, "boss")
    assert admin is not None
    assert admin.role == UserRole.ADMIN
    assert admin.hashed_password != "Secret1234"
    assert login(client, "boss", "Secret1234").status_code == 200

    entries = db.scalars(
        select(AuditLog).where(AuditLog.action == "create", AuditLog.entity_type == "user")
    ).all()
    assert [e.username for e in entries] == ["system"]


def test_existing_users_are_never_touched(db, users, monkeypatch):
    run_bootstrap(monkeypatch)
    assert db.get(User, "boss") is None


def test_a_short_password_is_rejected(db, monkeypatch):
    run_bootstrap(monkeypatch, password="short")
    assert db.get(User, "boss") is None


def test_nothing_happens_without_the_environment_variables(db, monkeypatch):
    monkeypatch.setattr(bootstrap, "SessionLocal", TestingSession)
    monkeypatch.delenv("ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    bootstrap.create_first_admin()

    assert db.scalars(select(User)).all() == []