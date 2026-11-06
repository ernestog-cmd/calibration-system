import csv
import enum
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import (
    CalibrationRecord,
    CalibrationResult,
    CalibrationState,
    Equipment,
    EquipmentStatus,
    EquipmentUsage,
)
from app.routers.usage import start_of_day_utc
from app.services.calibration import (
    compute_state,
    latest_pass_due_subquery,
    state_filter,
)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)

MAX_EXPORT_ROWS = 50_000


class SummaryRead(BaseModel):
    total_equipment: int
    by_status: dict[str, int]
    by_calibration_state: dict[str, int]
    usage_last_30_days: int


class FailedCalibrationRead(BaseModel):
    id: int
    equipment_id: int
    asset_code: str
    equipment_name: str
    calibration_date: date
    due_date: date
    result: CalibrationResult
    performed_by: str


def csv_safe(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, enum.Enum):
        value = value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        # Cells starting with these characters could run as formulas when opened in Excel
        if value[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value
    return str(value)


def csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow([csv_safe(value) for value in row])

    # The BOM makes Excel read the accents correctly
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def check_date_range(from_date: date | None, to_date: date | None) -> None:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_date cannot be later than to_date",
        )


@router.get("/summary", response_model=SummaryRead)
def summary(db: Session = Depends(get_db)):
    today = date.today()
    due_expr = latest_pass_due_subquery()
    rows = db.execute(
        select(Equipment.status, Equipment.requires_calibration, due_expr)
    ).all()

    by_status = {item.value: 0 for item in EquipmentStatus}
    by_state = {item.value: 0 for item in CalibrationState}
    for equipment_status, requires_calibration, due_date in rows:
        by_status[equipment_status.value] += 1
        # Retired equipment is left out of the calibration counts
        if equipment_status != EquipmentStatus.RETIRED:
            state = compute_state(requires_calibration, due_date, today)
            by_state[state.value] += 1

    since = datetime.now(timezone.utc) - timedelta(days=30)
    usage_count = db.scalar(
        select(func.count(EquipmentUsage.id)).where(EquipmentUsage.used_at >= since)
    )

    return SummaryRead(
        total_equipment=len(rows),
        by_status=by_status,
        by_calibration_state=by_state,
        usage_last_30_days=usage_count or 0,
    )


@router.get("/failed-calibrations", response_model=list[FailedCalibrationRead])
def failed_calibrations(
    from_date: date | None = None,
    to_date: date | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    check_date_range(from_date, to_date)

    query = (
        select(CalibrationRecord, Equipment.asset_code, Equipment.name)
        .join(Equipment, CalibrationRecord.equipment_id == Equipment.id)
        .where(CalibrationRecord.result != CalibrationResult.PASS)
    )
    if from_date:
        query = query.where(CalibrationRecord.calibration_date >= from_date)
    if to_date:
        query = query.where(CalibrationRecord.calibration_date <= to_date)

    query = (
        query.order_by(
            CalibrationRecord.calibration_date.desc(), CalibrationRecord.id.desc()
        )
        .offset(skip)
        .limit(limit)
    )
    rows = db.execute(query).all()

    return [
        FailedCalibrationRead(
            id=record.id,
            equipment_id=record.equipment_id,
            asset_code=asset_code,
            equipment_name=name,
            calibration_date=record.calibration_date,
            due_date=record.due_date,
            result=record.result,
            performed_by=record.performed_by,
        )
        for record, asset_code, name in rows
    ]


@router.get("/export/equipment")
def export_equipment(
    calibration_state: CalibrationState | None = None, db: Session = Depends(get_db)
):
    today = date.today()
    due_expr = latest_pass_due_subquery()
    query = select(Equipment, due_expr.label("latest_due_date"))
    if calibration_state:
        query = query.where(state_filter(calibration_state, due_expr, today))

    rows = db.execute(query.order_by(Equipment.asset_code).limit(MAX_EXPORT_ROWS)).all()

    header = [
        "asset_code",
        "name",
        "equipment_type",
        "serial_number",
        "location",
        "responsible_username",
        "requires_calibration",
        "calibration_interval_days",
        "status",
        "calibration_state",
        "calibration_due_date",
    ]
    data = [
        [
            equipment.asset_code,
            equipment.name,
            equipment.equipment_type,
            equipment.serial_number,
            equipment.location,
            equipment.responsible_username,
            equipment.requires_calibration,
            equipment.calibration_interval_days,
            equipment.status,
            compute_state(equipment.requires_calibration, due_date, today),
            due_date,
        ]
        for equipment, due_date in rows
    ]
    return csv_response(f"equipment_{today}.csv", header, data)


@router.get("/export/usage")
def export_usage(
    asset_code: str | None = None,
    lot_id: str | None = None,
    part_number: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
):
    check_date_range(from_date, to_date)

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

    rows = db.execute(
        query.order_by(EquipmentUsage.used_at.desc(), EquipmentUsage.id.desc()).limit(
            MAX_EXPORT_ROWS
        )
    ).all()

    header = [
        "used_at_utc",
        "asset_code",
        "equipment_name",
        "lot_id",
        "part_number",
        "operation",
        "notes",
        "calibration_state_at_use",
        "recorded_by",
    ]
    data = [
        [
            as_utc(usage.used_at),
            code,
            name,
            usage.lot_id,
            usage.part_number,
            usage.operation,
            usage.notes,
            usage.calibration_state_at_use,
            usage.recorded_by,
        ]
        for usage, code, name in rows
    ]
    return csv_response(f"usage_{date.today()}.csv", header, data)


@router.get("/export/calibrations")
def export_calibrations(
    from_date: date | None = None,
    to_date: date | None = None,
    result: CalibrationResult | None = None,
    db: Session = Depends(get_db),
):
    check_date_range(from_date, to_date)

    query = select(CalibrationRecord, Equipment.asset_code, Equipment.name).join(
        Equipment, CalibrationRecord.equipment_id == Equipment.id
    )
    if from_date:
        query = query.where(CalibrationRecord.calibration_date >= from_date)
    if to_date:
        query = query.where(CalibrationRecord.calibration_date <= to_date)
    if result:
        query = query.where(CalibrationRecord.result == result)

    rows = db.execute(
        query.order_by(
            CalibrationRecord.calibration_date.desc(), CalibrationRecord.id.desc()
        ).limit(MAX_EXPORT_ROWS)
    ).all()

    header = [
        "calibration_date",
        "due_date",
        "asset_code",
        "equipment_name",
        "result",
        "performed_by",
        "certificate_filename",
    ]
    data = [
        [
            record.calibration_date,
            record.due_date,
            code,
            name,
            record.result,
            record.performed_by,
            record.certificate_filename,
        ]
        for record, code, name in rows
    ]
    return csv_response(f"calibrations_{date.today()}.csv", header, data)