from datetime import date

from app.models import CalibrationState, EquipmentStatus
from app.services.alerts import AlertItem, build_digest, get_recipients, send_email
from tests.helpers import build_scenario, create_equipment


def make_fake_smtp(sent, fail=False):
    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            sent.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            sent.append(("starttls",))

        def login(self, user, password):
            sent.append(("login", user, password))

        def send_message(self, message):
            if fail:
                raise RuntimeError("boom")
            sent.append(("message", message["Subject"], message["To"]))

    return FakeSMTP


def configure_smtp(monkeypatch, smtp_class):
    monkeypatch.setattr("app.services.alerts.smtplib.SMTP", smtp_class)
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_RECIPIENTS", "a@example.com, b@example.com")


def test_alert_list_puts_expired_first_and_skips_retired_equipment(
    client, admin_h, tech_h, auditor_h
):
    build_scenario(client, admin_h, tech_h)

    response = client.get("/alerts/calibrations", headers=auditor_h)
    assert response.status_code == 200
    alerts = response.json()

    # Never calibrated first, then the expired one, then the one due soon
    assert [a["asset_code"] for a in alerts] == ["CAL-0004", "CAL-0003", "CAL-0002"]
    assert [a["calibration_state"] for a in alerts] == ["expired", "expired", "due_soon"]
    assert [a["days_remaining"] for a in alerts] == [None, -10, 20]


def test_running_the_job_without_smtp_only_generates_the_digest(
    client, admin_h, tech_h, monkeypatch
):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    build_scenario(client, admin_h, tech_h)

    response = client.post("/alerts/run", headers=admin_h)
    assert response.status_code == 200
    assert response.json() == {
        "expired": 2,
        "due_soon": 1,
        "email_sent": False,
        "error": None,
    }

    entries = client.get(
        "/audit", params={"action": "alert_digest_generated"}, headers=admin_h
    ).json()
    assert len(entries) == 1
    assert entries[0]["username"] == "system"
    assert entries[0]["new_value"] == {"expired": 2, "due_soon": 1}


def test_running_the_job_with_smtp_sends_the_email(client, admin_h, tech_h, monkeypatch):
    sent = []
    configure_smtp(monkeypatch, make_fake_smtp(sent))
    build_scenario(client, admin_h, tech_h)

    response = client.post("/alerts/run", headers=admin_h)
    assert response.json()["email_sent"] is True
    assert any(item[0] == "message" for item in sent)

    entries = client.get(
        "/audit", params={"action": "alert_digest_sent"}, headers=admin_h
    ).json()
    assert len(entries) == 1


def test_a_failing_email_is_reported_and_audited(client, admin_h, tech_h, monkeypatch):
    configure_smtp(monkeypatch, make_fake_smtp([], fail=True))
    create_equipment(client, admin_h)  # never calibrated, so there is one alert

    response = client.post("/alerts/run", headers=admin_h)
    assert response.status_code == 200
    body = response.json()
    assert body["email_sent"] is False
    assert body["error"] == "The email could not be sent"

    entries = client.get(
        "/audit", params={"action": "alert_digest_failed"}, headers=admin_h
    ).json()
    assert len(entries) == 1
    assert entries[0]["new_value"]["error"] == "boom"


def test_no_alerts_means_no_digest(client, admin_h, tech_h):
    response = client.post("/alerts/run", headers=admin_h)
    assert response.json() == {
        "expired": 0,
        "due_soon": 0,
        "email_sent": False,
        "error": None,
    }
    assert client.get("/audit", params={"entity_type": "system"}, headers=admin_h).json() == []


def test_only_admins_can_run_the_job(client, tech_h, auditor_h):
    assert client.post("/alerts/run", headers=tech_h).status_code == 403
    assert client.post("/alerts/run", headers=auditor_h).status_code == 403
    assert client.post("/alerts/run").status_code == 401
    assert client.get("/alerts/calibrations").status_code == 401


def test_email_goes_to_every_configured_recipient(monkeypatch):
    sent = []
    configure_smtp(monkeypatch, make_fake_smtp(sent))

    assert get_recipients() == ["a@example.com", "b@example.com"]
    assert send_email("Subject", "Body", get_recipients()) is True

    assert ("connect", "smtp.test", 2525) in sent
    assert ("starttls",) in sent
    assert ("login", "user", "pw") in sent
    assert ("message", "Subject", "a@example.com, b@example.com") in sent


def test_digest_lists_expired_before_due_soon():
    def item(code, state, due, days):
        return AlertItem(
            asset_code=code,
            name="Name",
            location="Line 1",
            responsible_username="tech1",
            status=EquipmentStatus.ACTIVE,
            calibration_state=state,
            calibration_due_date=due,
            days_remaining=days,
        )

    alerts = [
        item("CAL-2", CalibrationState.DUE_SOON, date(2026, 11, 20), 15),
        item("CAL-1", CalibrationState.EXPIRED, date(2026, 11, 1), -4),
    ]
    subject, body = build_digest(alerts, date(2026, 11, 5))

    assert subject == "Calibration alert 2026-11-05: 1 expired, 1 due soon"
    assert body.index("EXPIRED") < body.index("DUE SOON")
    assert "expired 4 days ago" in body
    assert "due in 15 days" in body