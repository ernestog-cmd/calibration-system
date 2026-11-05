from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import CalibrationRecord, CalibrationResult, CalibrationState, Equipment
from app.schemas import EquipmentBase, EquipmentRead

DUE_SOON_DAYS = 30


def compute_state(
    requires_calibration: bool, due_date: date | None, today: date
) -> CalibrationState:
    if not requires_calibration:
        return CalibrationState.NOT_REQUIRED
    if due_date is None or due_date < today:
        return CalibrationState.EXPIRED
    if due_date <= today + timedelta(days=DUE_SOON_DAYS):
        return CalibrationState.DUE_SOON
    return CalibrationState.VALID


def _latest_pass_due_stmt():
    # Due date of the most recent calibration that passed
    return (
        select(CalibrationRecord.due_date)
        .where(CalibrationRecord.result == CalibrationResult.PASS)
        .order_by(CalibrationRecord.calibration_date.desc(), CalibrationRecord.id.desc())
        .limit(1)
    )


def latest_pass_due_subquery():
    return (
        _latest_pass_due_stmt()
        .where(CalibrationRecord.equipment_id == Equipment.id)
        .correlate(Equipment)
        .scalar_subquery()
    )


def get_latest_pass_due_date(db: Session, equipment_id: int) -> date | None:
    return db.scalar(
        _latest_pass_due_stmt().where(CalibrationRecord.equipment_id == equipment_id)
    )


def state_filter(state: CalibrationState, due_expr, today: date):
    # Same rules as compute_state, written as SQL conditions
    if state == CalibrationState.NOT_REQUIRED:
        return Equipment.requires_calibration.is_(False)

    requires = Equipment.requires_calibration.is_(True)
    soon_limit = today + timedelta(days=DUE_SOON_DAYS)

    if state == CalibrationState.EXPIRED:
        return and_(requires, or_(due_expr.is_(None), due_expr < today))
    if state == CalibrationState.DUE_SOON:
        return and_(requires, due_expr >= today, due_expr <= soon_limit)
    return and_(requires, due_expr > soon_limit)


def to_equipment_read(
    equipment: Equipment, due_date: date | None, today: date | None = None
) -> EquipmentRead:
    today = today or date.today()
    base = EquipmentBase.model_validate(equipment).model_dump()
    return EquipmentRead(
        **base,
        calibration_state=compute_state(equipment.requires_calibration, due_date, today),
        calibration_due_date=due_date,
    )