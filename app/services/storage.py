import os
from pathlib import Path

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "uploads"))
CERTIFICATES_DIR = UPLOAD_DIR / "certificates"
MAX_CERTIFICATE_BYTES = 5 * 1024 * 1024


def ensure_storage() -> None:
    CERTIFICATES_DIR.mkdir(parents=True, exist_ok=True)


def certificate_path(calibration_id: int) -> Path:
    # The stored name depends only on the calibration id, never on user input
    return CERTIFICATES_DIR / f"calibration_{calibration_id}.pdf"