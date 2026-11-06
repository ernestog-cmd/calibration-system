import os
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.alerts import run_daily_alert_job


def start_scheduler() -> BackgroundScheduler | None:
    if os.getenv("ENABLE_SCHEDULER", "true").lower() != "true":
        return None

    timezone = ZoneInfo(os.getenv("ALERT_TIMEZONE", "America/Tijuana"))
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        run_daily_alert_job,
        CronTrigger(hour=int(os.getenv("ALERT_HOUR", "7")), minute=0, timezone=timezone),
        id="daily_calibration_alerts",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    return scheduler