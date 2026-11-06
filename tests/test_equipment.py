
import pytest

from app.models import User
from tests.helpers import (
    create_equipment,
    create_fixture,
    equipment_payload,
    fixture_payload,
)


def test_equipment_is_created_with_an_uppercase_code(client, admin_h):
    body = create_equipment(client, admin_h, asset_code="cal-0001")
    assert body["asset_code"] == "CAL-0001"
    assert body["status"] == "active"
    # Never calibrated, so equipment that requires calibration counts as expired
    assert body["calibration_state"] == "expired"
    assert body["calibration_due_date"] is None


def test_fixture_does_not_require_calibration(client, admin_h):
    body = create_fixture(client, admin_h)
    assert body["calibration_state"] == "not_required"
    assert body["calibration_interval_days"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"requires_calibration": True, "calibration_interval_days": None},
        {"requires_calibration": False, "calibration_interval_days": 365},
        {"calibration_interval_days": 0},
        {"calibration_interval_days": 5000},
        {"asset_code": "bad code!"},
        {"asset_code": "AB"},
    ],
)
def test_invalid_equipment_is_rejected(client, admin_h, overrides):
    response = client.post(
        "/equipment", json=equipment_payload(**overrides), headers=admin_h
    )
    assert response.status_code == 422


def test_duplicate_asset_code_is_a_conflict(client, admin_h):
    create_equipment(client, admin_h, asset_code="CAL-0001")
    response = client.post(
        "/equipment", json=equipment_payload(asset_code="cal-0001"), headers=admin_h
    )
    assert response.status_code == 409


def test_unknown_responsible_user_is_rejected(client, admin_h):
    response = client.post(
        "/equipment",
        json=equipment_payload(responsible_username="ghost"),
        headers=admin_h,
    )
    assert response.status_code == 400


def test_inactive_responsible_user_is_rejected(client, admin_h, db):
    db.get(User, "tech1").is_active = False
    db.commit()

    response = client.post("/equipment", json=equipment_payload(), headers=admin_h)
    assert response.status_code == 400


def test_only_admins_can_create_or_modify_equipment(client, admin_h, tech_h, auditor_h):
    equipment = create_equipment(client, admin_h)
    payload = equipment_payload(asset_code="CAL-0002")

    for headers in (tech_h, auditor_h):
        assert client.post("/equipment", json=payload, headers=headers).status_code == 403
        response = client.patch(
            f"/equipment/{equipment['id']}", json={"location": "Line 9"}, headers=headers
        )
        assert response.status_code == 403

    assert client.post("/equipment", json=payload).status_code == 401


def test_every_role_can_read_equipment(client, admin_h, tech_h, auditor_h):
    equipment = create_equipment(client, admin_h)
    for headers in (admin_h, tech_h, auditor_h):
        assert client.get("/equipment", headers=headers).status_code == 200
        assert client.get(f"/equipment/{equipment['id']}", headers=headers).status_code == 200
    assert client.get("/equipment").status_code == 401


def test_equipment_is_found_by_id_and_by_code(client, admin_h):
    equipment = create_equipment(client, admin_h, asset_code="CAL-0042")

    by_id = client.get(f"/equipment/{equipment['id']}", headers=admin_h)
    assert by_id.json()["asset_code"] == "CAL-0042"

    by_code = client.get("/equipment/by-code/cal-0042", headers=admin_h)
    assert by_code.status_code == 200
    assert by_code.json()["id"] == equipment["id"]

    assert client.get("/equipment/999", headers=admin_h).status_code == 404
    assert client.get("/equipment/by-code/NOPE-1", headers=admin_h).status_code == 404


def test_list_filters_and_pagination(client, admin_h, auditor_h):
    create_equipment(client, admin_h, asset_code="CAL-0001")
    create_equipment(
        client,
        admin_h,
        asset_code="CAL-0002",
        name="Torque wrench",
        equipment_type="torque wrench",
        location="Line 2",
        serial_number="SN-0002",
    )
    create_fixture(client, admin_h, location="Line 1")

    def codes(**params):
        response = client.get("/equipment", params=params, headers=auditor_h)
        assert response.status_code == 200
        return [item["asset_code"] for item in response.json()]

    assert codes() == ["CAL-0001", "CAL-0002", "FIX-0001"]
    assert codes(q="wrench") == ["CAL-0002"]
    assert codes(q="cal-0001") == ["CAL-0001"]
    assert codes(equipment_type="FIXTURE") == ["FIX-0001"]
    assert codes(location="line 1") == ["CAL-0001", "FIX-0001"]
    assert codes(requires_calibration="false") == ["FIX-0001"]
    assert codes(responsible_username="tech1") == ["CAL-0001", "CAL-0002", "FIX-0001"]
    assert codes(status="out_of_service") == []
    assert codes(limit=1, skip=1) == ["CAL-0002"]


def test_patch_changes_only_the_fields_that_were_sent(client, admin_h):
    equipment = create_equipment(client, admin_h)
    response = client.patch(
        f"/equipment/{equipment['id']}", json={"location": "Line 2"}, headers=admin_h
    )
    assert response.status_code == 200
    body = response.json()
    assert body["location"] == "Line 2"
    assert body["name"] == equipment["name"]


def test_turning_calibration_on_requires_an_interval(client, admin_h):
    fixture = create_fixture(client, admin_h)
    url = f"/equipment/{fixture['id']}"

    assert client.patch(url, json={"requires_calibration": True}, headers=admin_h).status_code == 400

    response = client.patch(
        url,
        json={"requires_calibration": True, "calibration_interval_days": 180},
        headers=admin_h,
    )
    assert response.status_code == 200
    assert response.json()["calibration_state"] == "expired"


def test_turning_calibration_off_clears_the_interval(client, admin_h):
    equipment = create_equipment(client, admin_h)
    response = client.patch(
        f"/equipment/{equipment['id']}",
        json={"requires_calibration": False},
        headers=admin_h,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["calibration_interval_days"] is None
    assert body["calibration_state"] == "not_required"


def test_interval_cannot_be_set_on_equipment_without_calibration(client, admin_h):
    fixture = create_fixture(client, admin_h)
    response = client.patch(
        f"/equipment/{fixture['id']}",
        json={"calibration_interval_days": 30},
        headers=admin_h,
    )
    assert response.status_code == 400


def test_changing_to_a_taken_code_is_a_conflict(client, admin_h):
    create_equipment(client, admin_h, asset_code="CAL-0001")
    second = create_equipment(client, admin_h, asset_code="CAL-0002")

    response = client.patch(
        f"/equipment/{second['id']}", json={"asset_code": "cal-0001"}, headers=admin_h
    )
    assert response.status_code == 409


def test_keeping_the_same_code_is_not_a_conflict(client, admin_h):
    equipment = create_equipment(client, admin_h, asset_code="CAL-0001")
    response = client.patch(
        f"/equipment/{equipment['id']}", json={"asset_code": "cal-0001"}, headers=admin_h
    )
    assert response.status_code == 200