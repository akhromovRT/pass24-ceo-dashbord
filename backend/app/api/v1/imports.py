import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import ImportRun
from app.parser.debt_report import parse_debt_report
from app.services.import_service import ImportService

router = APIRouter(
    prefix="/import",
    tags=["import"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload")
def upload_file(
    file: UploadFile,
    session: Session = Depends(get_session),
):
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    with tempfile.NamedTemporaryFile(
        suffix=Path(file.filename).suffix, delete=False
    ) as tmp:
        content = file.file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        parse_result = parse_debt_report(tmp_path)
    except ValueError as e:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Parse error: {e}")

    # Check duplicate by file hash
    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == parse_result.file_hash)
    ).first()
    if existing:
        Path(tmp_path).unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail="File already imported")

    parse_result.filename = file.filename
    svc = ImportService(session)
    import_run = svc.process_import(parse_result)
    Path(tmp_path).unlink(missing_ok=True)

    return import_run


@router.get("/runs")
def list_import_runs(session: Session = Depends(get_session)):
    runs = session.exec(
        select(ImportRun).order_by(ImportRun.started_at.desc())  # type: ignore[union-attr]
    ).all()
    return runs
