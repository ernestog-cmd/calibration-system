from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import EquipmentStatus, UserRole


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


class EquipmentRead(BaseModel):
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