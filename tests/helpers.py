from datetime import date, timedelta

PASSWORD = "Secret123"


def days_ago(days: int) -> date:
    return date.today() - timedelta(days=days)


def login(client, username, password=PASSWORD):
    return client.post(
        "/auth/login", data={"username": username, "password": password}
    )


def equipment_payload(**overrides):
    payload = {
        "asset_code": "CAL-0001",
        "name": "Digital caliper",
        "equipment_type": "caliper",
        "serial_number": "SN-0001",
        "location": "Line 1",
        "responsible_username": "tech1",
        "requires_calibration": True,
        "calibration_interval_days": 365,
    }
    return {**payload, **overrides}


def fixture_payload(**overrides):
    return equipment_payload(
        **{
            "asset_code": "FIX-0001",
            "name": "Assembly fixture",
            "equipment_type": "fixture",
            "serial_number": "FX-0001",
            "requires_calibration": False,
            "calibration_interval_days": None,
            **overrides,
        }
    )


def create_equipment(client, headers, **overrides):
    response = client.post(
        "/equipment", json=equipment_payload(**overrides), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_fixture(client, headers, **overrides):
    response = client.post(
        "/equipment", json=fixture_payload(**overrides), headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def calibrate(client, headers, equipment_id, on, result="pass", **extra):
    return client.post(
        f"/equipment/{equipment_id}/calibrations",
        json={"calibration_date": on.isoformat(), "result": result, **extra},
        headers=headers,
    )


def record_usage(client, headers, asset_code, lot_id="LOT-1", **extra):
    return client.post(
        "/usage",
        json={"asset_code": asset_code, "lot_id": lot_id, **extra},
        headers=headers,
    )


def build_scenario(client, admin_h, tech_h):
    """Six pieces of equipment in different calibration situations."""
    valid = create_equipment(client, admin_h, asset_code="CAL-0001")
    soon = create_equipment(
        client, admin_h, asset_code="CAL-0002", calibration_interval_days=30
    )
    expired = create_equipment(
        client, admin_h, asset_code="CAL-0003", calibration_interval_days=30
    )
    never = create_equipment(client, admin_h, asset_code="CAL-0004")
    retired = create_equipment(client, admin_h, asset_code="CAL-0005")
    fixture = create_fixture(client, admin_h)

    calibrate(client, tech_h, valid["id"], days_ago(0))
    calibrate(client, tech_h, soon["id"], days_ago(10))
    calibrate(client, tech_h, expired["id"], days_ago(40))
    response = client.patch(
        f"/equipment/{retired['id']}", json={"status": "retired"}, headers=admin_h
    )
    assert response.status_code == 200, response.text

    return {
        "valid": valid,
        "soon": soon,
        "expired": expired,
        "never": never,
        "retired": retired,
        "fixture": fixture,
    }