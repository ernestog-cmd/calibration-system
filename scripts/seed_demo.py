import os
import random
import secrets
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (
    CalibrationRecord,
    CalibrationResult,
    Equipment,
    EquipmentStatus,
    EquipmentUsage,
    User,
    UserRole,
)
from app.security import hash_password
from app.services.audit import log_action, snapshot
from app.services.calibration import compute_state

EQUIPMENT_TYPES = [
    ("Digital caliper", "caliper", 365),
    ("Micrometer", "micrometer", 365),
    ("Torque wrench", "torque wrench", 180),
    ("Multimeter", "multimeter", 365),
    ("Precision scale", "scale", 180),
    ("Digital thermometer", "thermometer", 365),
    ("Temperature chamber", "temperature chamber", 180),
]
LOCATIONS = ["Line 1", "Line 2", "Line 3", "Quality lab"]
# Mostly valid equipment, with a few in every other situation
SCENARIOS = [
    "valid", "valid", "valid", "valid", "valid", "due_soon",
    "valid", "expired", "valid", "failed", "valid", "never",
]
FIXTURE_NAMES = [
    "Assembly fixture A",
    "Assembly fixture B",
    "Test fixture C",
    "Holding fixture D",
]
PARTS = ["PN-1001", "PN-1002", "PN-2001", "PN-3050"]
OPERATIONS = [
    "Incoming inspection",
    "In-process check",
    "Final inspection",
    "Assembly",
    "Functional test",
]
TECHNICIANS = ["tech1", "tech2"]


def seed() -> None:
    rng = random.Random(2026)  # the same demo data on every run
    today = date.today()
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(Equipment)):
            print("Seed skipped: the database already has equipment.")
            return

        password = os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(9)
        hashed = hash_password(password)
        for username, first_name, last_name, role in (
            ("tech1", "Alex", "Ramos", UserRole.TECHNICIAN),
            ("tech2", "Maria", "Lopez", UserRole.TECHNICIAN),
            ("auditor1", "Sam", "Cruz", UserRole.AUDITOR),
        ):
            if db.get(User, username) is None:
                user = User(
                    username=username,
                    hashed_password=hashed,
                    first_name=first_name,
                    last_name=last_name,
                    role=role,
                )
                db.add(user)
                db.flush()
                log_action(
                    db, "seed", "create", "user", username, None,
                    snapshot(user, exclude=("hashed_password",)),
                )

        due_by_id: dict[int, date | None] = {}
        usable: list[Equipment] = []

        def add_equipment(code, name, equipment_type, interval, requires):
            equipment = Equipment(
                asset_code=code,
                name=name,
                equipment_type=equipment_type,
                serial_number=f"SN-{rng.randint(10000, 99999)}",
                location=rng.choice(LOCATIONS),
                responsible_username=rng.choice(TECHNICIANS),
                requires_calibration=requires,
                calibration_interval_days=interval,
            )
            db.add(equipment)
            db.flush()
            log_action(db, "seed", "create", "equipment", equipment.id, None, snapshot(equipment))
            return equipment

        def add_calibration(equipment, days_ago, result):
            calibration_date = today - timedelta(days=days_ago)
            record = CalibrationRecord(
                equipment_id=equipment.id,
                calibration_date=calibration_date,
                due_date=calibration_date + timedelta(days=equipment.calibration_interval_days),
                result=result,
                performed_by=rng.choice(TECHNICIANS),
            )
            db.add(record)
            db.flush()
            log_action(db, "seed", "create", "calibration", record.id, None, snapshot(record))
            return record

        for index in range(24):
            name, equipment_type, interval = EQUIPMENT_TYPES[index % len(EQUIPMENT_TYPES)]
            scenario = SCENARIOS[index % len(SCENARIOS)]
            equipment = add_equipment(
                f"CAL-{index + 1:04d}", f"{name} {index + 1}", equipment_type, interval, True
            )

            last_pass_due = None
            if scenario in ("valid", "due_soon", "expired"):
                if scenario == "valid":
                    days = rng.randint(5, interval - 60)
                elif scenario == "due_soon":
                    days = interval - 15
                else:
                    days = interval + 20
                add_calibration(equipment, days + interval, CalibrationResult.PASS)  # history
                last_pass_due = add_calibration(equipment, days, CalibrationResult.PASS).due_date
            elif scenario == "failed":
                last_pass_due = add_calibration(
                    equipment, interval - 100, CalibrationResult.PASS
                ).due_date
                add_calibration(equipment, 3, CalibrationResult.FAIL)
                equipment.status = EquipmentStatus.OUT_OF_SERVICE
                log_action(
                    db, "seed", "auto_out_of_service", "equipment", equipment.id,
                    {"status": "active"}, {"status": "out_of_service"},
                )

            due_by_id[equipment.id] = last_pass_due
            state = compute_state(True, last_pass_due, today)
            if equipment.status == EquipmentStatus.ACTIVE and state.value != "expired":
                usable.append(equipment)

        for number, fixture_name in enumerate(FIXTURE_NAMES, start=1):
            fixture = add_equipment(f"FIX-{number:04d}", fixture_name, "fixture", None, False)
            due_by_id[fixture.id] = None
            usable.append(fixture)

        for lot_number in range(101, 113):
            lot_id = f"LOT-2026-{lot_number:04d}"
            part_number = rng.choice(PARTS)
            day = rng.randint(0, 29)
            for equipment in rng.sample(usable, rng.randint(3, 5)):
                usage = EquipmentUsage(
                    equipment_id=equipment.id,
                    lot_id=lot_id,
                    part_number=part_number,
                    operation=rng.choice(OPERATIONS),
                    calibration_state_at_use=compute_state(
                        equipment.requires_calibration, due_by_id[equipment.id], today
                    ),
                    used_at=now - timedelta(days=day, hours=rng.randint(0, 8), minutes=rng.randint(0, 59)),
                    recorded_by=rng.choice(TECHNICIANS),
                )
                db.add(usage)
                db.flush()
                log_action(db, "seed", "create", "usage", usage.id, None, snapshot(usage))

        db.commit()

    print("Demo data loaded: 28 equipment, calibration history and lot usage.")
    print("Demo users: tech1, tech2 (technicians) and auditor1 (auditor).")
    print(f"Demo password: {password}")


if __name__ == "__main__":
    seed()