from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.helpers import calibrate, create_equipment, days_ago, record_usage


def audit(client, headers, **params):
    response = client.get("/audit", params={"limit": 200, **params}, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_creating_equipment_is_audited(client, admin_h):
    equipment = create_equipment(client, admin_h, asset_code="cal-0001")

    entries = audit(client, admin_h, entity_type="equipment", action="create")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["username"] == "admin1"
    assert entry["entity_id"] == str(equipment["id"])
    assert entry["old_value"] is None
    assert entry["new_value"]["asset_code"] == "CAL-0001"


def test_updates_record_only_the_fields_that_changed(client, admin_h):
    equipment = create_equipment(client, admin_h)

    client.patch(
        f"/equipment/{equipment['id']}",
        json={"location": "Line 2", "name": equipment["name"]},
        headers=admin_h,
    )

    entries = audit(client, admin_h, entity_type="equipment", action="update")
    assert len(entries) == 1
    assert entries[0]["old_value"] == {"location": "Line 1"}
    assert entries[0]["new_value"] == {"location": "Line 2"}


def test_an_update_that_changes_nothing_is_not_logged(client, admin_h):
    equipment = create_equipment(client, admin_h)

    client.patch(
        f"/equipment/{equipment['id']}", json={"location": "Line 1"}, headers=admin_h
    )

    assert audit(client, admin_h, entity_type="equipment", action="update") == []


def test_password_hashes_never_reach_the_audit_log(client, admin_h):
    client.post(
        "/users",
        json={
            "username": "newtech",
            "password": "Secret123",
            "first_name": "New",
            "last_name": "Tech",
            "role": "technician",
        },
        headers=admin_h,
    )
    client.patch("/users/newtech", json={"password": "NewSecret456"}, headers=admin_h)

    entries = audit(client, admin_h, entity_type="user")
    text = str(entries)
    assert "hashed_password" not in text
    assert "$2b$" not in text
    assert "NewSecret456" not in text

    update = audit(client, admin_h, entity_type="user", action="update")[0]
    assert update["new_value"] == {"password": "[changed]"}


def test_calibrations_and_usage_are_audited(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], date.today())
    record_usage(client, tech_h, "CAL-0001", lot_id="lot-1")

    calibration = audit(client, admin_h, entity_type="calibration", action="create")
    assert len(calibration) == 1
    assert calibration[0]["username"] == "tech1"
    assert calibration[0]["new_value"]["result"] == "pass"

    usage = audit(client, admin_h, entity_type="usage", action="create")
    assert len(usage) == 1
    assert usage[0]["new_value"]["lot_id"] == "LOT-1"


def test_automatic_out_of_service_is_logged_as_its_own_entry(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], days_ago(2))
    calibrate(client, tech_h, equipment["id"], date.today(), "fail")

    entries = audit(client, admin_h, action="auto_out_of_service")
    assert len(entries) == 1
    assert entries[0]["entity_type"] == "equipment"
    assert entries[0]["entity_id"] == str(equipment["id"])
    assert entries[0]["username"] == "tech1"
    assert entries[0]["old_value"] == {"status": "active"}
    assert entries[0]["new_value"] == {"status": "out_of_service"}


def test_audit_log_filters(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], date.today())

    by_user = audit(client, admin_h, username="tech1")
    assert by_user and all(entry["username"] == "tech1" for entry in by_user)

    by_entity = audit(client, admin_h, entity_type="calibration", entity_id="1")
    assert len(by_entity) == 1

    response = client.get(
        "/audit",
        params={"from_date": "2026-11-10", "to_date": "2026-11-01"},
        headers=admin_h,
    )
    assert response.status_code == 400


def test_only_admins_and_auditors_can_read_the_audit_log(client, admin_h, tech_h, auditor_h):
    assert client.get("/audit", headers=admin_h).status_code == 200
    assert client.get("/audit", headers=auditor_h).status_code == 200
    assert client.get("/audit", headers=tech_h).status_code == 403
    assert client.get("/audit").status_code == 401


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_there_is_no_way_to_write_to_the_audit_log_through_the_api(client, admin_h, method):
    response = getattr(client, method)("/audit", headers=admin_h)
    assert response.status_code == 405


def test_audit_entries_cannot_be_modified_or_deleted(client, admin_h, db):
    create_equipment(client, admin_h)

    entry = db.scalars(select(AuditLog)).first()
    entry.action = "tampered"
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()

    entry = db.scalars(select(AuditLog)).first()
    db.delete(entry)
    with pytest.raises(RuntimeError):
        db.commit()
    db.rollback()