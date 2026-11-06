import hashlib
from datetime import date

from app.services import storage
from tests.helpers import calibrate, create_equipment

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n"


def setup_calibration(client, admin_h, tech_h):
    equipment = create_equipment(client, admin_h)
    response = calibrate(client, tech_h, equipment["id"], date.today())
    assert response.status_code == 201
    return equipment, response.json()


def certificate_url(equipment, calibration):
    return f"/equipment/{equipment['id']}/calibrations/{calibration['id']}/certificate"


def upload(client, headers, url, content=PDF, filename="cert.pdf"):
    return client.post(
        url, files={"file": (filename, content, "application/pdf")}, headers=headers
    )


def test_certificate_can_be_uploaded_and_downloaded(client, admin_h, tech_h, auditor_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    response = upload(client, tech_h, url)
    assert response.status_code == 201
    assert response.json()["certificate_filename"] == "cert.pdf"

    download = client.get(url, headers=auditor_h)
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content == PDF


def test_a_certificate_can_only_be_uploaded_once(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    assert upload(client, tech_h, url).status_code == 201
    assert upload(client, tech_h, url).status_code == 409


def test_files_that_are_not_pdfs_are_rejected(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    response = upload(client, tech_h, url, content=b"just some text", filename="fake.pdf")
    assert response.status_code == 400


def test_large_files_are_rejected(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    too_big = b"%PDF-" + b"0" * (5 * 1024 * 1024 + 1)
    assert upload(client, tech_h, url, content=too_big).status_code == 413


def test_download_without_a_certificate_is_not_found(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    assert client.get(certificate_url(equipment, calibration), headers=tech_h).status_code == 404


def test_certificate_permissions(client, admin_h, tech_h, auditor_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    assert upload(client, auditor_h, url).status_code == 403
    assert upload(client, admin_h, url).status_code == 201
    assert client.get(url).status_code == 401


def test_calibration_must_belong_to_the_equipment(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)

    wrong_equipment = f"/equipment/999/calibrations/{calibration['id']}/certificate"
    assert upload(client, tech_h, wrong_equipment).status_code == 404

    wrong_calibration = f"/equipment/{equipment['id']}/calibrations/999/certificate"
    assert upload(client, tech_h, wrong_calibration).status_code == 404


def test_the_uploaded_file_name_never_decides_where_it_is_stored(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    url = certificate_url(equipment, calibration)

    response = upload(client, tech_h, url, filename="../../evil.pdf")
    assert response.status_code == 201
    assert response.json()["certificate_filename"] == "evil.pdf"

    stored = storage.CERTIFICATES_DIR / f"calibration_{calibration['id']}.pdf"
    assert stored.exists()
    assert [p.name for p in storage.CERTIFICATES_DIR.iterdir()] == [stored.name]


def test_upload_is_audited_with_the_file_hash(client, admin_h, tech_h):
    equipment, calibration = setup_calibration(client, admin_h, tech_h)
    upload(client, tech_h, certificate_url(equipment, calibration))

    entries = client.get(
        "/audit", params={"action": "upload_certificate"}, headers=admin_h
    ).json()
    assert len(entries) == 1
    assert entries[0]["new_value"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    assert entries[0]["new_value"]["size_bytes"] == len(PDF)