from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import UserRole


def check_password_bytes(value: str | None) -> str | None:
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