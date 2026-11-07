import logging
import os
import re

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password
from app.services.audit import log_action, snapshot

logger = logging.getLogger("calibration.bootstrap")


def create_first_admin() -> None:
    username = os.getenv("ADMIN_USERNAME", "").strip()
    password = os.getenv("ADMIN_PASSWORD", "")
    if not username or not password:
        return

    with SessionLocal() as db:
        # Only runs on an empty system, so existing users are never touched
        if db.scalar(select(func.count()).select_from(User)):
            return

        if not re.fullmatch(r"[a-zA-Z0-9_.-]{3,50}", username):
            logger.error("ADMIN_USERNAME is not valid; the first admin was not created")
            return
        if len(password) < 8 or len(password.encode("utf-8")) > 72:
            logger.error("ADMIN_PASSWORD must be 8 to 72 bytes; the first admin was not created")
            return

        user = User(
            username=username,
            hashed_password=hash_password(password),
            first_name=os.getenv("ADMIN_FIRST_NAME", "Admin"),
            last_name=os.getenv("ADMIN_LAST_NAME", "User"),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.flush()
        log_action(
            db,
            "system",
            "create",
            "user",
            user.username,
            None,
            snapshot(user, exclude=("hashed_password",)),
        )
        db.commit()
        logger.info("First admin user '%s' created", username)


def maybe_seed_demo_data() -> None:
    if os.getenv("SEED_DEMO_DATA", "false").lower() != "true":
        return

    from scripts.seed_demo import seed

    seed()