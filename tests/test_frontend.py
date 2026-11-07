def test_root_redirects_to_the_interface(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/ui/"


def test_interface_files_are_served(client):
    page = client.get("/ui/")
    assert page.status_code == 200
    assert "Calibration System" in page.text

    for path in (
        "/ui/css/styles.css",
        "/ui/js/app.js",
        "/ui/js/api.js",
        "/ui/js/ui.js",
        "/ui/js/views/dashboard.js",
        "/ui/js/views/equipment.js",
    ):
        assert client.get(path).status_code == 200, path