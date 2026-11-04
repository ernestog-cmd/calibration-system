from pydantic import BaseModel, ConfigDict
from app.models import UserRole

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
