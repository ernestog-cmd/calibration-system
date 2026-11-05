from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import CalibrationState, Equipment, EquipmentStatus, User, UserRole
from app.schemas import EquipmentCreate, EquipmentRead, EquipmentUpdate
from app.services.audit import diff, log_action, snapshot
from app.services.calibration import (
    get_latest_pass_due_date,
    latest_pass_due_subquery,
    state_filter,
    to_equipment_read,
)

# Every endpoint needs a valid login; writing endpoints use the admin-only check below
router = APIRouter(
    prefix="/equipment",
    tags=["equipment"],
    dependencies=[Depends(get_current_user)],
)

admin_only = Depends(require_roles(UserRole.ADMIN))


def get_equipment_or_404(db: Session, equipment_id: int) -> Equipment:
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return equipment


def ensure_active_user(db: Session, username: str) -> None:
    user = db.get(User, username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The responsible user does not exist or is inactive",
        )


def ensure_asset_code_is_free(db: Session, asset_code: str) -> None:
    exists = db.scalar(select(Equipment.id).where(Equipment.asset_code == asset_code))
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That asset code already exists",
        )


@router.post("", response_model=EquipmentRead, status_code=status.HTTP_201_CREATED)
def create_equipment(
    data: EquipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = admin_only,
):
    ensure_asset_code_is_free(db, data.asset_code)
    ensure_active_user(db, data.responsible_username)

    equipment = Equipment(**data.model_dump())
    db.add(equipment)
    db.flush()
    log_action(
        db,
        current_user.username,
        "create",
        "equipment",
        equipment.id,
        None,
        snapshot(equipment),
    )
    db.commit()
    db.refresh(equipment)
    return to_equipment_read(equipment, due_date=None)


@router.get("", response_model=list[EquipmentRead])
def list_equipment(
    q: str | None = None,
    equipment_type: str | None = None,
    location: str | None = None,
    status_filter: EquipmentStatus | None = Query(default=None, alias="status"),
    calibration_state: CalibrationState | None = None,
    requires_calibration: bool | None = None,
    responsible_username: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    today = date.today()
    due_expr = latest_pass_due_subquery()
    query = select(Equipment, due_expr.label("latest_due_date"))

    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(
                Equipment.asset_code.ilike(pattern),
                Equipment.name.ilike(pattern),
                Equipment.serial_number.ilike(pattern),
            )
        )
    if equipment_type:
        query = query.where(
            func.lower(Equipment.equipment_type) == equipment_type.lower()
        )
    if location:
        query = query.where(func.lower(Equipment.location) == location.lower())
    if status_filter:
        query = query.where(Equipment.status == status_filter)
    if calibration_state:
        query = query.where(state_filter(calibration_state, due_expr, today))
    if requires_calibration is not None:
        query = query.where(Equipment.requires_calibration == requires_calibration)
    if responsible_username:
        query = query.where(Equipment.responsible_username == responsible_username)

    query = query.order_by(Equipment.asset_code).offset(skip).limit(limit)
    rows = db.execute(query).all()
    return [to_equipment_read(equipment, due, today) for equipment, due in rows]


# This route goes before /{equipment_id} so the two paths never get mixed up
@router.get("/by-code/{asset_code}", response_model=EquipmentRead)
def get_equipment_by_code(asset_code: str, db: Session = Depends(get_db)):
    equipment = db.scalar(
        select(Equipment).where(Equipment.asset_code == asset_code.upper())
    )
    if equipment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Equipment not found"
        )
    return to_equipment_read(equipment, get_latest_pass_due_date(db, equipment.id))


@router.get("/{equipment_id}", response_model=EquipmentRead)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)):
    equipment = get_equipment_or_404(db, equipment_id)
    return to_equipment_read(equipment, get_latest_pass_due_date(db, equipment.id))


@router.patch("/{equipment_id}", response_model=EquipmentRead)
def update_equipment(
    equipment_id: int,
    data: EquipmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = admin_only,
):
    equipment = get_equipment_or_404(db, equipment_id)
    changes = data.model_dump(exclude_none=True)

    if "asset_code" in changes and changes["asset_code"] != equipment.asset_code:
        ensure_asset_code_is_free(db, changes["asset_code"])

    if "responsible_username" in changes:
        ensure_active_user(db, changes["responsible_username"])

    # Validate the final combination, not only the fields that were sent
    requires_calibration = changes.get(
        "requires_calibration", equipment.requires_calibration
    )
    if requires_calibration:
        interval = changes.get(
            "calibration_interval_days", equipment.calibration_interval_days
        )
        if interval is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="calibration_interval_days is required when the equipment requires calibration",
            )
    else:
        if "calibration_interval_days" in changes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="calibration_interval_days must be empty when the equipment does not require calibration",
            )
        changes["calibration_interval_days"] = None

    old_value, new_value = diff(equipment, changes)

    for field, value in changes.items():
        setattr(equipment, field, value)

    if new_value:
        log_action(
            db,
            current_user.username,
            "update",
            "equipment",
            equipment.id,
            old_value,
            new_value,
        )

    db.commit()
    db.refresh(equipment)
    return to_equipment_read(equipment, get_latest_pass_due_date(db, equipment.id))