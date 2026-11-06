import csv
import io
from datetime import date

from tests.helpers import (
    build_scenario,
    calibrate,
    create_equipment,
    days_ago,
    record_usage,
)


def read_csv(response):
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_reports_require_login(client):
    assert client.get("/reports/summary").status_code == 401
    assert client.get("/reports/export/equipment").status_code == 401


def test_summary_counts_equipment_by_status_and_calibration_state(
    client, admin_h, tech_h, auditor_h
):
    build_scenario(client, admin_h, tech_h)
    assert record_usage(client, tech_h, "CAL-0001").status_code == 201
    assert record_usage(client, tech_h, "FIX-0001").status_code == 201

    response = client.get("/reports/summary", headers=auditor_h)
    assert response.status_code == 200
    body = response.json()

    assert body["total_equipment"] == 6
    assert body["by_status"] == {"active": 5, "out_of_service": 0, "retired": 1}
    # The retired piece of equipment is left out of the calibration counts
    assert body["by_calibration_state"] == {
        "valid": 1,
        "due_soon": 1,
        "expired": 2,
        "not_required": 1,
    }
    assert body["usage_last_30_days"] == 2


def test_failed_calibrations_are_listed_newest_first(client, admin_h, tech_h, auditor_h):
    first = create_equipment(client, admin_h, asset_code="CAL-0001")
    second = create_equipment(client, admin_h, asset_code="CAL-0002")
    calibrate(client, tech_h, first["id"], days_ago(10))
    calibrate(client, tech_h, first["id"], days_ago(5), "fail")
    calibrate(client, tech_h, second["id"], date.today(), "out_of_tolerance")

    response = client.get("/reports/failed-calibrations", headers=auditor_h)
    assert response.status_code == 200
    items = response.json()
    assert [i["asset_code"] for i in items] == ["CAL-0002", "CAL-0001"]
    assert [i["result"] for i in items] == ["out_of_tolerance", "fail"]

    recent = client.get(
        "/reports/failed-calibrations",
        params={"from_date": days_ago(2).isoformat()},
        headers=auditor_h,
    )
    assert [i["asset_code"] for i in recent.json()] == ["CAL-0002"]

    invalid = client.get(
        "/reports/failed-calibrations",
        params={"from_date": "2026-11-10", "to_date": "2026-11-01"},
        headers=auditor_h,
    )
    assert invalid.status_code == 400


def test_equipment_export_is_a_csv_that_excel_can_open(client, admin_h, tech_h, auditor_h):
    build_scenario(client, admin_h, tech_h)

    response = client.get("/reports/export/equipment", headers=auditor_h)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")

    rows = read_csv(response)
    assert len(rows) == 6
    assert rows[0]["asset_code"] == "CAL-0001"
    assert rows[0]["calibration_state"] == "valid"

    # The state filter does not look at the administrative status, so the
    # retired, never calibrated piece of equipment is listed as expired too
    expired = client.get(
        "/reports/export/equipment",
        params={"calibration_state": "expired"},
        headers=auditor_h,
    )
    assert [r["asset_code"] for r in read_csv(expired)] == ["CAL-0003", "CAL-0004", "CAL-0005"]


def test_usage_export_neutralizes_formulas_and_applies_filters(
    client, admin_h, tech_h, auditor_h
):
    build_scenario(client, admin_h, tech_h)
    record_usage(client, tech_h, "CAL-0001", lot_id="LOT-1", operation="@evil", notes="=1+1")
    record_usage(client, tech_h, "CAL-0001", lot_id="LOT-2")

    everything = read_csv(client.get("/reports/export/usage", headers=auditor_h))
    assert len(everything) == 2

    one_lot = client.get(
        "/reports/export/usage", params={"lot_id": "lot-1"}, headers=auditor_h
    )
    rows = read_csv(one_lot)
    assert len(rows) == 1
    # Cells that start with a formula character are prefixed so Excel does not run them
    assert rows[0]["notes"] == "'=1+1"
    assert rows[0]["operation"] == "'@evil"

    invalid = client.get(
        "/reports/export/usage",
        params={"from_date": "2026-11-10", "to_date": "2026-11-01"},
        headers=auditor_h,
    )
    assert invalid.status_code == 400


def test_calibration_export_can_be_filtered_by_result(client, admin_h, tech_h, auditor_h):
    equipment = create_equipment(client, admin_h)
    calibrate(client, tech_h, equipment["id"], days_ago(3))
    calibrate(client, tech_h, equipment["id"], date.today(), "fail")

    everything = read_csv(client.get("/reports/export/calibrations", headers=auditor_h))
    assert len(everything) == 2

    failed = client.get(
        "/reports/export/calibrations", params={"result": "fail"}, headers=auditor_h
    )
    rows = read_csv(failed)
    assert len(rows) == 1
    assert rows[0]["result"] == "fail"

    invalid = client.get(
        "/reports/export/calibrations",
        params={"from_date": "2026-11-10", "to_date": "2026-11-01"},
        headers=auditor_h,
    )
    assert invalid.status_code == 400