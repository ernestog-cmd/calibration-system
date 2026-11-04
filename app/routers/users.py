from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import UserCreate, UserRead, UserUpdate
from app.security import hash_password

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    if db.get(User, data.username) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That username already exists"
        )

    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.username)).all()


@router.get("/{username}", response_model=UserRead)
def get_user(username: str, db: Session = Depends(get_db)):
    user = db.get(User, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{username}", response_model=UserRead)
def update_user(
    username: str,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    changes = data.model_dump(exclude_none=True)

    # An admin cannot lock themselves out of the system by mistake
    if user.username == current_user.username:
        if changes.get("is_active") is False or (
            "role" in changes and changes["role"] != UserRole.ADMIN
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot deactivate or demote your own account",
            )

    if "password" in changes:
        user.hashed_password = hash_password(changes.pop("password"))

    for field, value in changes.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user