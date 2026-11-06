from datetime import date, datetime, timedelta, timezone

import pytest

from tests.helpers import (
    calibrate,
    create_equipment,
    create_fixture,
    days_ago,
    record_usage,
)


def ready_equipment(client, admin_h, tech_h, **overrides):
    equipment = create_equipment(client, admin_h, **overrides)
    assert calibrate(client, tech_h, equipment["id"], date.today()).status_code == 201
    return equipment


def test_usage_is_recorded_with_normalized_identifiers(client, admin_h, tech_h):
    ready_equipment(client, admin_h, tech_h)

    response = record_usage(
        client,
        tech_h,
        "cal-0001",
        lot_id="lot-1",
        part_number="pn-55",
        operation="Final inspection",
        notes="Dimensional check",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["asset_code"] == "CAL-0001"
    assert body["lot_id"] == "LOT-1"
    assert body["part_number"] == "PN-55"
    assert body["calibration_state_at_use"] == "valid"
    assert body["recorded_by"] == "tech1"
    assert body["used_at"].endswith(("Z", "+00:00"))


def test_equipment_due_soon_can_still_be_used(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h, calibration_interval_days=30)
    calibrate(client, tech_h, equipment["id"], days_ago(10))

    response = record_usage(client, tech_h, "CAL-0001")
    assert response.status_code == 201
    assert response.json()["calibration_state_at_use"] == "due_soon"


def test_fixture_can_be_used_without_calibration(client, admin_h, tech_h):
    create_fixture(client, admin_h)

    response = record_usage(client, tech_h, "FIX-0001")
    assert response.status_code == 201
    assert response.json()["calibration_state_at_use"] == "not_required"


def test_expired_equipment_is_blocked(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h, calibration_interval_days=30)
    calibrate(client, tech_h, equipment["id"], days_ago(40))

    response = record_usage(client, tech_h, "CAL-0001")
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]


def test_equipment_never_calibrated_is_blocked(client, admin_h, tech_h):
    create_equipment(client, admin_h)

    response = record_usage(client, tech_h, "CAL-0001")
    assert response.status_code == 409
    assert "no passed calibration" in response.json()["detail"]


def test_equipment_out_of_service_is_blocked(client, admin_h, tech_h):
    equipment = ready_equipment(client, admin_h, tech_h)
    calibrate(client, tech_h, equipment["id"], date.today(), "fail")

    response = record_usage(client, tech_h, "CAL-0001")
    assert response.status_code == 409
    assert "out of service" in response.json()["detail"]


def test_retired_equipment_is_blocked(client, admin_h, tech_h):
    equipment = ready_equipment(client, admin_h, tech_h)
    client.patch(
        f"/equipment/{equipment['id']}", json={"status": "retired"}, headers=admin_h
    )

    response = record_usage(client, tech_h, "CAL-0001")
    assert response.status_code == 409
    assert "retired" in response.json()["detail"]


def test_usage_input_errors_and_permissions(client, admin_h, tech_h, auditor_h):
    ready_equipment(client, admin_h, tech_h)

    assert record_usage(client, tech_h, "NOPE-1").status_code == 404
    assert record_usage(client, tech_h, "bad code!").status_code == 422
    assert record_usage(client, auditor_h, "CAL-0001").status_code == 403
    assert record_usage(client, admin_h, "CAL-0001").status_code == 201
    assert client.post("/usage", json={"asset_code": "CAL-0001", "lot_id": "L"}).status_code == 401


def test_usage_can_be_searched_in_both_directions(client, admin_h, tech_h, auditor_h):
    ready_equipment(client, admin_h, tech_h, asset_code="CAL-0001")
    create_fixture(client, admin_h)

    record_usage(client, tech_h, "CAL-0001", lot_id="LOT-1", part_number="PN-A")
    record_usage(client, tech_h, "FIX-0001", lot_id="LOT-1")
    record_usage(client, tech_h, "CAL-0001", lot_id="LOT-2", part_number="PN-B")

    def search(**params):
        response = client.get("/usage", params=params, headers=auditor_h)
        assert response.status_code == 200
        return response.json()

    # Where was this equipment used?
    assert len(search(asset_code="cal-0001")) == 2
    # Which equipment took part in this lot?
    assert {u["asset_code"] for u in search(lot_id="lot-1")} == {"CAL-0001", "FIX-0001"}
    assert len(search(part_number="pn-b")) == 1
    assert len(search(asset_code="CAL-0001", lot_id="LOT-2")) == 1
    assert search(lot_id="LOT-99") == []
    # Newest first
    assert search()[0]["lot_id"] == "LOT-2"


def test_usage_date_range_uses_utc_days(client, admin_h, tech_h, auditor_h):
    ready_equipment(client, admin_h, tech_h)
    record_usage(client, tech_h, "CAL-0001")

    utc_today = datetime.now(timezone.utc).date()

    def count(**params):
        response = client.get("/usage", params=params, headers=auditor_h)
        assert response.status_code == 200
        return len(response.json())

    assert count(from_date=utc_today.isoformat(), to_date=utc_today.isoformat()) == 1
    assert count(from_date=(utc_today + timedelta(days=1)).isoformat()) == 0
    assert count(to_date=(utc_today - timedelta(days=1)).isoformat()) == 0

    response = client.get(
        "/usage",
        params={"from_date": "2026-11-10", "to_date": "2026-11-01"},
        headers=auditor_h,
    )
    assert response.status_code == 400


@pytest.mark.parametrize("method", ["get", "post"])
def test_usage_requires_login(client, method):
    response = getattr(client, method)("/usage")
    assert response.status_code == 401