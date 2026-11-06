import logging
import os
import smtplib
from datetime import date
from email.message import EmailMessage

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import CalibrationState, Equipment, EquipmentStatus
from app.services.audit import log_action
from app.services.calibration import compute_state, latest_pass_due_subquery

logger = logging.getLogger("calibration.alerts")


class AlertItem(BaseModel):
    asset_code: str
    name: str
    location: str
    responsible_username: str
    status: EquipmentStatus
    calibration_state: CalibrationState
    calibration_due_date: date | None
    # Negative when already expired, empty when the equipment was never calibrated
    days_remaining: int | None


def collect_alerts(db: Session, today: date | None = None) -> list[AlertItem]:
    today = today or date.today()
    due_expr = latest_pass_due_subquery()

    rows = db.execute(
        select(Equipment, due_expr.label("latest_due_date"))
        .where(
            Equipment.requires_calibration.is_(True),
            Equipment.status != EquipmentStatus.RETIRED,
        )
        .order_by(Equipment.asset_code)
    ).all()

    alerts = []
    for equipment, due_date in rows:
        state = compute_state(True, due_date, today)
        if state in (CalibrationState.EXPIRED, CalibrationState.DUE_SOON):
            alerts.append(
                AlertItem(
                    asset_code=equipment.asset_code,
                    name=equipment.name,
                    location=equipment.location,
                    responsible_username=equipment.responsible_username,
                    status=equipment.status,
                    calibration_state=state,
                    calibration_due_date=due_date,
                    days_remaining=(due_date - today).days if due_date else None,
                )
            )

    # Expired first, then by due date
    alerts.sort(
        key=lambda a: (
            a.calibration_state != CalibrationState.EXPIRED,
            a.calibration_due_date or date.min,
        )
    )
    return alerts


def describe(alert: AlertItem) -> str:
    if alert.calibration_due_date is None:
        when = "no passed calibration on record"
    elif alert.days_remaining < 0:
        when = f"expired {-alert.days_remaining} days ago (due {alert.calibration_due_date})"
    else:
        when = f"due in {alert.days_remaining} days ({alert.calibration_due_date})"
    return (
        f"- {alert.asset_code} | {alert.name} | {alert.location} | "
        f"responsible: {alert.responsible_username} | {when}"
    )


def build_digest(alerts: list[AlertItem], today: date) -> tuple[str, str]:
    expired = [a for a in alerts if a.calibration_state == CalibrationState.EXPIRED]
    due_soon = [a for a in alerts if a.calibration_state == CalibrationState.DUE_SOON]

    subject = (
        f"Calibration alert {today}: {len(expired)} expired, {len(due_soon)} due soon"
    )

    sections = []
    if expired:
        sections.append("EXPIRED\n" + "\n".join(describe(a) for a in expired))
    if due_soon:
        sections.append("DUE SOON\n" + "\n".join(describe(a) for a in due_soon))

    return subject, "\n\n".join(sections)


def get_recipients() -> list[str]:
    raw = os.getenv("ALERT_RECIPIENTS", "")
    return [email.strip() for email in raw.split(",") if email.strip()]


def send_email(subject: str, body: str, recipients: list[str]) -> bool:
    host = os.getenv("SMTP_HOST")
    if not host or not recipients:
        # Development mode: without SMTP settings the digest is only written to the log
        logger.info("Email not sent (no SMTP_HOST or ALERT_RECIPIENTS)\n%s\n\n%s", subject, body)
        return False

    user = os.getenv("SMTP_USER")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("SMTP_FROM", user or "calibration-system@localhost")
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=20) as smtp:
        if os.getenv("SMTP_STARTTLS", "true").lower() == "true":
            smtp.starttls()
        if user:
            smtp.login(user, os.getenv("SMTP_PASSWORD", ""))
        smtp.send_message(message)

    return True


def run_alert_job(db: Session, today: date | None = None) -> dict:
    today = today or date.today()
    alerts = collect_alerts(db, today)

    expired = sum(1 for a in alerts if a.calibration_state == CalibrationState.EXPIRED)
    due_soon = len(alerts) - expired
    result = {"expired": expired, "due_soon": due_soon, "email_sent": False, "error": None}

    if not alerts:
        logger.info("No calibration alerts for %s", today)
        return result

    subject, body = build_digest(alerts, today)
    counts = {"expired": expired, "due_soon": due_soon}

    try:
        result["email_sent"] = send_email(subject, body, get_recipients())
        action = "alert_digest_sent" if result["email_sent"] else "alert_digest_generated"
        log_action(db, "system", action, "system", str(today), None, counts)
    except Exception as exc:
        logger.exception("Could not send the calibration alert email")
        result["error"] = "The email could not be sent"
        log_action(
            db,
            "system",
            "alert_digest_failed",
            "system",
            str(today),
            None,
            {**counts, "error": str(exc)[:200]},
        )

    db.commit()
    return result


def run_daily_alert_job() -> None:
    with SessionLocal() as db:
        run_alert_job(db)