from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import (
    CalibrationState,
    Equipment,
    EquipmentStatus,
    EquipmentUsage,
    User,
    UserRole,
)
from app.schemas import UsageBase, UsageCreate, UsageRead
from app.services.audit import log_action, snapshot
from app.services.calibration import compute_state, get_latest_pass_due_date

router = APIRouter(
    prefix="/usage",
    tags=["usage"],
    dependencies=[Depends(get_current_user)],
)


def to_usage_read(usage: EquipmentUsage, asset_code: str, name: str) -> UsageRead:
    base = UsageBase.model_validate(usage).model_dump()
    return UsageRead(**base, asset_code=asset_code, equipment_name=name)


def start_of_day_utc(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc)


@router.post("", response_model=UsageRead, status_code=status.HTTP_201_CREATED)
def record_usage(
    data: UsageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    equipment = db.scalar(
        select(Equipment).where(Equipment.asset_code == data.asset_code)
    )
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )

    if equipment.status != EquipmentStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The equipment is {equipment.status.value.replace('_', ' ')} and cannot be used",
        )

    due_date = get_latest_pass_due_date(db, equipment.id)
    state = compute_state(equipment.requires_calibration, due_date, date.today())
    if state == CalibrationState.EXPIRED:
        reason = (
            "it has no passed calibration on record"
            if due_date is None
            else f"its calibration expired on {due_date}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"The equipment cannot be used: {reason}",
        )

    usage = EquipmentUsage(
        equipment_id=equipment.id,
        lot_id=data.lot_id,
        part_number=data.part_number,
        operation=data.operation,
        notes=data.notes,
        calibration_state_at_use=state,
        recorded_by=current_user.username,
    )
    db.add(usage)
    db.flush()
    log_action(
        db,
        current_user.username,
        "create",
        "usage",
        usage.id,
        None,
        snapshot(usage),
    )
    db.commit()
    db.refresh(usage)
    return to_usage_read(usage, equipment.asset_code, equipment.name)


@router.get("", response_model=list[UsageRead])
def search_usage(
    asset_code: str | None = None,
    lot_id: str | None = None,
    part_number: str | None = None,
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

    query = select(EquipmentUsage, Equipment.asset_code, Equipment.name).join(
        Equipment, EquipmentUsage.equipment_id == Equipment.id
    )

    if asset_code:
        query = query.where(Equipment.asset_code == asset_code.strip().upper())
    if lot_id:
        query = query.where(EquipmentUsage.lot_id == lot_id.strip().upper())
    if part_number:
        query = query.where(EquipmentUsage.part_number == part_number.strip().upper())
    if from_date:
        query = query.where(EquipmentUsage.used_at >= start_of_day_utc(from_date))
    if to_date:
        query = query.where(
            EquipmentUsage.used_at < start_of_day_utc(to_date + timedelta(days=1))
        )

    query = (
        query.order_by(EquipmentUsage.used_at.desc(), EquipmentUsage.id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = db.execute(query).all()
    return [to_usage_read(usage, code, name) for usage, code, name in rows]