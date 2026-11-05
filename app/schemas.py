from datetime import date, datetime, timezone

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import CalibrationResult, CalibrationState, EquipmentStatus, UserRole


def check_password_bytes(value: str | None) -> str | None:
    # bcrypt only uses the first 72 bytes, so longer passwords are rejected
    if value is not None and len(value.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes long")
    return value


class Token(BaseModel):
    access_token: str
    token_type: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    first_name: str
    last_name: str
    role: UserRole
    is_active: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    role: UserRole

    _validate_password = field_validator("password")(check_password_bytes)


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8)
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    is_active: bool | None = None

    _validate_password = field_validator("password")(check_password_bytes)


class EquipmentCreate(BaseModel):
    asset_code: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(min_length=1, max_length=150)
    equipment_type: str = Field(min_length=1, max_length=100)
    serial_number: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=100)
    responsible_username: str
    requires_calibration: bool = True
    calibration_interval_days: int | None = Field(default=None, gt=0, le=3650)

    @field_validator("asset_code")
    @classmethod
    def uppercase_asset_code(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def check_calibration_interval(self):
        if self.requires_calibration and self.calibration_interval_days is None:
            raise ValueError(
                "calibration_interval_days is required when requires_calibration is true"
            )
        if not self.requires_calibration and self.calibration_interval_days is not None:
            raise ValueError(
                "calibration_interval_days must be empty when requires_calibration is false"
            )
        return self


class EquipmentUpdate(BaseModel):
    asset_code: str | None = Field(
        default=None, min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$"
    )
    name: str | None = Field(default=None, min_length=1, max_length=150)
    equipment_type: str | None = Field(default=None, min_length=1, max_length=100)
    serial_number: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    responsible_username: str | None = None
    requires_calibration: bool | None = None
    calibration_interval_days: int | None = Field(default=None, gt=0, le=3650)
    status: EquipmentStatus | None = None

    @field_validator("asset_code")
    @classmethod
    def uppercase_asset_code(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class EquipmentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    name: str
    equipment_type: str
    serial_number: str
    location: str
    responsible_username: str
    requires_calibration: bool
    calibration_interval_days: int | None
    status: EquipmentStatus


class EquipmentRead(EquipmentBase):
    calibration_state: CalibrationState
    calibration_due_date: date | None


class CalibrationCreate(BaseModel):
    calibration_date: date
    result: CalibrationResult
    certificate_filename: str | None = Field(default=None, min_length=1, max_length=255)


class CalibrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    calibration_date: date
    due_date: date
    result: CalibrationResult
    performed_by: str
    certificate_filename: str | None


class UsageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    asset_code: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    lot_id: str = Field(min_length=1, max_length=100)
    part_number: str | None = Field(default=None, min_length=1, max_length=100)
    operation: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("asset_code", "lot_id", "part_number")
    @classmethod
    def uppercase_identifiers(cls, value: str | None) -> str | None:
        return value.upper() if value is not None else None


class UsageBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    equipment_id: int
    lot_id: str
    part_number: str | None
    operation: str | None
    notes: str | None
    calibration_state_at_use: CalibrationState
    used_at: datetime
    recorded_by: str

    @field_validator("used_at")
    @classmethod
    def ensure_utc(cls, value: datetime) -> datetime:
        # SQLite returns datetimes without timezone; they are always stored in UTC
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class UsageRead(UsageBase):
    asset_code: str
    equipment_name: str