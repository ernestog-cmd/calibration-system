from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import (
    CalibrationRecord,
    CalibrationResult,
    Equipment,
    EquipmentStatus,
    User,
    UserRole,
)
from app.schemas import CalibrationCreate, CalibrationRead

router = APIRouter(
    prefix="/equipment/{equipment_id}/calibrations",
    tags=["calibrations"],
    dependencies=[Depends(get_current_user)],
)


def get_equipment_or_404(db: Session, equipment_id: int) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return equipment


@router.post("", response_model=CalibrationRead, status_code=status.HTTP_201_CREATED)
def create_calibration(
    equipment_id: int,
    data: CalibrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    equipment = get_equipment_or_404(db, equipment_id)

    if not equipment.requires_calibration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This equipment does not require calibration",
        )
    if equipment.status == EquipmentStatus.RETIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A retired equipment cannot be calibrated",
        )
    if data.calibration_date > date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The calibration date cannot be in the future",
        )

    last_date = db.scalar(
        select(func.max(CalibrationRecord.calibration_date)).where(
            CalibrationRecord.equipment_id == equipment.id
        )
    )
    if last_date is not None and data.calibration_date < last_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The calibration date cannot be earlier than the last one ({last_date})",
        )

    record = CalibrationRecord(
        equipment_id=equipment.id,
        calibration_date=data.calibration_date,
        due_date=data.calibration_date
        + timedelta(days=equipment.calibration_interval_days),
        result=data.result,
        performed_by=current_user.username,
        certificate_filename=data.certificate_filename,
    )

    # A failed calibration takes the equipment out of service automatically.
    # Bringing it back is a deliberate action by an admin (PATCH status to active).
    if data.result != CalibrationResult.PASS and equipment.status == EquipmentStatus.ACTIVE:
        equipment.status = EquipmentStatus.OUT_OF_SERVICE

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("", response_model=list[CalibrationRead])
def list_calibrations(
    equipment_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    get_equipment_or_404(db, equipment_id)

    query = (
        select(CalibrationRecord)
        .where(CalibrationRecord.equipment_id == equipment_id)
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(query).all()