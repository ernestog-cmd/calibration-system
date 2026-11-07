import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_migrations_build_the_whole_schema_from_scratch(tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_URL": db_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    tables = set(inspect(create_engine(db_url)).get_table_names())
    assert {
        "users",
        "equipment",
        "calibration_records",
        "equipment_usage",
        "audit_log",
    } <= tables