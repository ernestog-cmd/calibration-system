from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_roles
from app.models import AuditLog, UserRole

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.AUDITOR))],
)


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    username: str
    action: str
    entity_type: str
    entity_id: str
    old_value: dict | None
    new_value: dict | None

    @field_validator("timestamp")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        # SQLite returns datetimes without timezone; they are always stored in UTC
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def start_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


@router.get("", response_model=list[AuditRead])
def search_audit_log(
    username: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be later than to_date",
        )

    query = select(AuditLog)

    if username:
        query = query.where(AuditLog.username == username)
    if action:
        query = query.where(AuditLog.action == action)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if from_date:
        query = query.where(AuditLog.timestamp >= start_of_day_utc(from_date))
    if to_date:
        query = query.where(
            AuditLog.timestamp < start_of_day_utc(to_date + timedelta(days=1))
        )

    query = (
        query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(query).all()