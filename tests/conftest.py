import os
import shutil
import tempfile

# These settings must be in place before the app is imported
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="calibration-tests-")
for _name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_RECIPIENTS"):
    os.environ.pop(_name, None)

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, UserRole
from app.security import create_access_token, hash_password
from app.services import storage
from tests.helpers import PASSWORD

# Hashing is slow on purpose, so it is done once and shared by every test user
PASSWORD_HASH = hash_password(PASSWORD)

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    shutil.rmtree(storage.CERTIFICATES_DIR, ignore_errors=True)
    yield


@pytest.fixture
def db():
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def users(db):
    for username, role in (
        ("admin1", UserRole.ADMIN),
        ("tech1", UserRole.TECHNICIAN),
        ("auditor1", UserRole.AUDITOR),
    ):
        db.add(
            User(
                username=username,
                hashed_password=PASSWORD_HASH,
                first_name="Test",
                last_name=username.title(),
                role=role,
            )
        )
    db.commit()


def auth_header(username: str, role: UserRole) -> dict:
    return {"Authorization": f"Bearer {create_access_token(username, role.value)}"}


@pytest.fixture
def admin_h(users):
    return auth_header("admin1", UserRole.ADMIN)


@pytest.fixture
def tech_h(users):
    return auth_header("tech1", UserRole.TECHNICIAN)


@pytest.fixture
def auditor_h(users):
    return auth_header("auditor1", UserRole.AUDITOR)