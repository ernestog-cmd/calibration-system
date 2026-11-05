import enum
from datetime import date, datetime

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models import AuditLog


def jsonable(value):
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def snapshot(obj, exclude: tuple[str, ...] = ()) -> dict:
    return {
        column.name: jsonable(getattr(obj, column.name))
        for column in obj.__table__.columns
        if column.name not in exclude
    }


def diff(obj, changes: dict) -> tuple[dict, dict]:
    # Keeps only the fields whose value really changes
    old_value, new_value = {}, {}
    for field, value in changes.items():
        before, after = jsonable(getattr(obj, field)), jsonable(value)
        if before != after:
            old_value[field] = before
            new_value[field] = after
    return old_value, new_value


def log_action(
    db: Session,
    username: str,
    action: str,
    entity_type: str,
    entity_id,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    # Added to the session without committing, so the entry is saved in the same
    # transaction as the change it describes
    db.add(
        AuditLog(
            username=username[:50],
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id)[:50],
            old_value=old_value,
            new_value=new_value,
        )
    )


@event.listens_for(AuditLog, "before_update")
def block_audit_update(mapper, connection, target):
    raise RuntimeError("Audit log entries cannot be modified")


@event.listens_for(AuditLog, "before_delete")
def block_audit_delete(mapper, connection, target):
    raise RuntimeError("Audit log entries cannot be deleted")