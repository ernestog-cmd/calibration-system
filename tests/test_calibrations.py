from datetime import date, timedelta

import pytest

from tests.helpers import (
    calibrate,
    create_equipment,
    create_fixture,
    days_ago,
    equipment_payload,
    fixture_payload,
)


def get_equipment(client, headers, equipment_id):
    response = client.get(f"/equipment/{equipment_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_passed_calibration_sets_the_due_date_from_the_interval(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h, calibration_interval_days=365)

    response = calibrate(
        client, tech_h, equipment["id"], date.today(), certificate_filename="CERT-1.pdf"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["due_date"] == (date.today() + timedelta(days=365)).isoformat()
    assert body["performed_by"] == "tech1"
    assert body["certificate_filename"] == "CERT-1.pdf"

    current = get_equipment(client, tech_h, equipment["id"])
    assert current["calibration_state"] == "valid"
    assert current["calibration_due_date"] == body["due_date"]


@pytest.mark.parametrize(
    "interval, calibrated_days_ago, expected",
    [
        (365, 0, "valid"),
        (31, 0, "valid"),
        (30, 0, "due_soon"),
        (30, 10, "due_soon"),
        (30, 30, "due_soon"),
        (30, 31, "expired"),
        (30, 40, "expired"),
    ],
)
def test_calibration_state_follows_the_due_date(
    client, admin_h, tech_h, interval, calibrated_days_ago, expected
):
    equipment = create_equipment(client, admin_h, calibration_interval_days=interval)
    response = calibrate(client, tech_h, equipment["id"], days_ago(calibrated_days_ago))
    assert response.status_code == 201

    current = get_equipment(client, tech_h, equipment["id"])
    assert current["calibration_state"] == expected


def test_failed_calibration_takes_equipment_out_of_service_but_keeps_the_last_pass(
    client, admin_h, tech_h
):
    equipment = create_equipment(client, admin_h, calibration_interval_days=365)
    calibrate(client, tech_h, equipment["id"], days_ago(5))
    response = calibrate(client, tech_h, equipment["id"], date.today(), "fail")
    assert response.status_code == 201

    current = get_equipment(client, admin_h, equipment["id"])
    assert current["status"] == "out_of_service"
    # The state still comes from the last calibration that passed
    assert current["calibration_state"] == "valid"
    assert current["calibration_due_date"] == (days_ago(5) + timedelta(days=365)).isoformat()


def test_equipment_that_never_passed_is_expired(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], date.today(), "fail")

    current = get_equipment(client, admin_h, equipment["id"])
    assert current["status"] == "out_of_service"
    assert current["calibration_state"] == "expired"
    assert current["calibration_due_date"] is None


def test_out_of_tolerance_also_takes_equipment_out_of_service(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], date.today(), "out_of_tolerance")

    assert get_equipment(client, admin_h, equipment["id"])["status"] == "out_of_service"


def test_a_pass_does_not_bring_equipment_back_into_service(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], date.today(), "fail")
    calibrate(client, tech_h, equipment["id"], date.today(), "pass")

    assert get_equipment(client, admin_h, equipment["id"])["status"] == "out_of_service"

    response = client.patch(
        f"/equipment/{equipment['id']}", json={"status": "active"}, headers=admin_h
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_future_date_is_rejected(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    tomorrow = date.today() + timedelta(days=1)
    assert calibrate(client, tech_h, equipment["id"], tomorrow).status_code == 400


def test_date_earlier_than_the_last_calibration_is_rejected(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    assert calibrate(client, tech_h, equipment["id"], days_ago(5)).status_code == 201
    assert calibrate(client, tech_h, equipment["id"], days_ago(10)).status_code == 400


def test_two_calibrations_on_the_same_day_are_allowed(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    assert calibrate(client, tech_h, equipment["id"], days_ago(5), "fail").status_code == 201
    assert calibrate(client, tech_h, equipment["id"], days_ago(5), "pass").status_code == 201


def test_fixture_cannot_be_calibrated(client, admin_h, tech_h):
    fixture = create_fixture(client, admin_h)
    assert calibrate(client, tech_h, fixture["id"], date.today()).status_code == 400


def test_retired_equipment_cannot_be_calibrated(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    client.patch(
        f"/equipment/{equipment['id']}", json={"status": "retired"}, headers=admin_h
    )
    assert calibrate(client, tech_h, equipment["id"], date.today()).status_code == 400


def test_calibration_permissions(client, admin_h, tech_h, auditor_h):
    equipment = create_equipment(client, admin_h)

    assert calibrate(client, auditor_h, equipment["id"], date.today()).status_code == 403
    assert calibrate(client, admin_h, equipment["id"], date.today()).status_code == 201
    assert calibrate(client, tech_h, equipment["id"], date.today()).status_code == 201

    unauthenticated = client.post(
        f"/equipment/{equipment['id']}/calibrations",
        json={"calibration_date": date.today().isoformat(), "result": "pass"},
    )
    assert unauthenticated.status_code == 401


def test_calibration_input_errors(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)

    assert calibrate(client, tech_h, 999, date.today()).status_code == 404
    assert calibrate(client, tech_h, equipment["id"], date.today(), "maybe").status_code == 422


def test_history_is_listed_newest_first(client, admin_h, tech_h, auditor_h):
    equipment = create_equipment(client, admin_h)
    for days in (30, 20, 10):
        assert calibrate(client, tech_h, equipment["id"], days_ago(days)).status_code == 201

    response = client.get(f"/equipment/{equipment['id']}/calibrations", headers=auditor_h)
    assert response.status_code == 200
    dates = [item["calibration_date"] for item in response.json()]
    assert dates == [days_ago(10).isoformat(), days_ago(20).isoformat(), days_ago(30).isoformat()]

    assert client.get("/equipment/999/calibrations", headers=auditor_h).status_code == 404


def test_list_can_be_filtered_by_calibration_state(client, admin_h, tech_h):
    valid = create_equipment(client, admin_h, asset_code="CAL-0001")
    soon = create_equipment(client, admin_h, asset_code="CAL-0002", calibration_interval_days=30)
    expired = create_equipment(client, admin_h, asset_code="CAL-0003", calibration_interval_days=30)
    create_equipment(client, admin_h, asset_code="CAL-0004")  # never calibrated
    client.post("/equipment", json=fixture_payload(), headers=admin_h)

    calibrate(client, tech_h, valid["id"], date.today())
    calibrate(client, tech_h, soon["id"], days_ago(10))
    calibrate(client, tech_h, expired["id"], days_ago(40))

    def codes(state):
        response = client.get(
            "/equipment", params={"calibration_state": state}, headers=tech_h
        )
        assert response.status_code == 200
        return [item["asset_code"] for item in response.json()]

    assert codes("valid") == ["CAL-0001"]
    assert codes("due_soon") == ["CAL-0002"]
    assert codes("expired") == ["CAL-0003", "CAL-0004"]
    assert codes("not_required") == ["FIX-0001"]