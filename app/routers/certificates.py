import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import CalibrationRecord, User, UserRole
from app.schemas import CalibrationRead
from app.services.audit import log_action
from app.services.storage import MAX_CERTIFICATE_BYTES, certificate_path, ensure_storage

router = APIRouter(
    prefix="/equipment/{equipment_id}/calibrations/{calibration_id}/certificate",
    tags=["certificates"],
    dependencies=[Depends(get_current_user)],
)


def get_calibration_or_404(
    db: Session, equipment_id: int, calibration_id: int
) -> CalibrationRecord:
    record = db.scalar(
        select(CalibrationRecord).where(
            CalibrationRecord.id == calibration_id,
            CalibrationRecord.equipment_id == equipment_id,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Calibration not found"
        )
    return record


@router.post("", response_model=CalibrationRead, status_code=status.HTTP_201_CREATED)
def upload_certificate(
    equipment_id: int,
    calibration_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.TECHNICIAN)),
):
    record = get_calibration_or_404(db, equipment_id, calibration_id)
    path = certificate_path(record.id)

    if path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This calibration already has a certificate",
        )

    content = file.file.read(MAX_CERTIFICATE_BYTES + 1)
    if len(content) > MAX_CERTIFICATE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="The certificate cannot be larger than 5 MB",
        )
    # Checking the content is more reliable than trusting the extension or content type
    if not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="The file is not a valid PDF"
        )

    original_name = Path((file.filename or "").replace("\\", "/")).name[:255]
    filename = original_name or f"calibration_{record.id}.pdf"

    ensure_storage()
    try:
        with open(path, "xb") as stored_file:
            stored_file.write(content)
    except FileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This calibration already has a certificate",
        )

    try:
        old_filename = record.certificate_filename
        record.certificate_filename = filename
        log_action(
            db,
            current_user.username,
            "upload_certificate",
            "calibration",
            record.id,
            {"certificate_filename": old_filename},
            {
                "certificate_filename": filename,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise

    db.refresh(record)
    return record


@router.get("")
def download_certificate(
    equipment_id: int, calibration_id: int, db: Session = Depends(get_db)
):
    record = get_calibration_or_404(db, equipment_id, calibration_id)
    path = certificate_path(record.id)

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This calibration has no certificate file",
        )

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=record.certificate_filename or path.name,
    )