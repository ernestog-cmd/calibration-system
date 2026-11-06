from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import UserRole
from app.services.alerts import AlertItem, collect_alerts, run_alert_job

router = APIRouter(
    prefix="/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


class AlertRunResult(BaseModel):
    expired: int
    due_soon: int
    email_sent: bool
    error: str | None


@router.get("/calibrations", response_model=list[AlertItem])
def list_calibration_alerts(db: Session = Depends(get_db)):
    return collect_alerts(db)


@router.post(
    "/run",
    response_model=AlertRunResult,
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)
def run_alerts_now(db: Session = Depends(get_db)):
    return run_alert_job(db)