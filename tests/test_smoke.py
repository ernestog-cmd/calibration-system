def test_health_endpoint_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_builds_and_lists_every_router(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200

    paths = response.json()["paths"]
    for expected in (
        "/health",
        "/auth/login",
        "/users",
        "/equipment",
        "/equipment/{equipment_id}/calibrations",
        "/equipment/{equipment_id}/calibrations/{calibration_id}/certificate",
        "/usage",
        "/alerts/calibrations",
        "/reports/summary",
        "/audit",
    ):
        assert expected in paths