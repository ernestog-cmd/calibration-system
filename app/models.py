import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TECHNICIAN = "technician"
    AUDITOR = "auditor"


class EquipmentStatus(str, enum.Enum):
    ACTIVE = "active"
    OUT_OF_SERVICE = "out_of_service"
    RETIRED = "retired"


class CalibrationResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    OUT_OF_TOLERANCE = "out_of_tolerance"


class CalibrationState(str, enum.Enum):
    VALID = "valid"
    DUE_SOON = "due_soon"
    EXPIRED = "expired"
    NOT_REQUIRED = "not_required"


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    equipment_type: Mapped[str] = mapped_column(String(100), index=True)
    serial_number: Mapped[str] = mapped_column(String(100))
    location: Mapped[str] = mapped_column(String(100))
    responsible_username: Mapped[str] = mapped_column(ForeignKey("users.username"))
    requires_calibration: Mapped[bool] = mapped_column(Boolean, default=True)
    # Empty for equipment that does not require calibration (fixtures, tooling)
    calibration_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[EquipmentStatus] = mapped_column(
        Enum(EquipmentStatus), default=EquipmentStatus.ACTIVE
    )

    calibrations: Mapped[list["CalibrationRecord"]] = relationship(
        back_populates="equipment",
        order_by=lambda: CalibrationRecord.calibration_date.desc(),
    )
    usages: Mapped[list["EquipmentUsage"]] = relationship(back_populates="equipment")


class CalibrationRecord(Base):
    __tablename__ = "calibration_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    calibration_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    result: Mapped[CalibrationResult] = mapped_column(Enum(CalibrationResult))
    performed_by: Mapped[str] = mapped_column(ForeignKey("users.username"))
    certificate_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    equipment: Mapped["Equipment"] = relationship(back_populates="calibrations")


class EquipmentUsage(Base):
    __tablename__ = "equipment_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    # Plain text on purpose: this project does not depend on the lot traceability database
    lot_id: Mapped[str] = mapped_column(String(100), index=True)
    part_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    operation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Snapshot of the equipment calibration state at the moment of use, kept for history
    calibration_state_at_use: Mapped[CalibrationState] = mapped_column(
        Enum(CalibrationState)
    )
    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.username"))

    equipment: Mapped["Equipment"] = relationship(back_populates="usages")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    username: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(50))
    entity_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)