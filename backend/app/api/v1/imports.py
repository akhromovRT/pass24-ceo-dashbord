import hashlib
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import ImportRun
from app.parser.bank_statement import parse_bank_statement
from app.parser.debt_report import parse_debt_report
from app.parser.registry import parse_registry
from app.services.import_service import ImportService

router = APIRouter(
    prefix="/import",
    tags=["import"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/upload")
def upload_file(
    file: UploadFile,
    source_type: Literal["debt", "bank", "registry"] = Query(default="debt"),
    session: Session = Depends(get_session),
):
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    content = file.file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == file_hash)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="File already imported")

    with tempfile.NamedTemporaryFile(
        suffix=Path(file.filename).suffix, delete=False
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    svc = ImportService(session)
    try:
        if source_type == "debt":
            try:
                parse_result = parse_debt_report(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            parse_result.filename = file.filename
            import_run = svc.process_import(parse_result)
        elif source_type == "bank":
            try:
                bank_result = parse_bank_statement(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            bank_result.filename = file.filename
            import_run = svc.process_bank_import(bank_result, file_hash=file_hash)
        elif source_type == "registry":
            try:
                reg_result = parse_registry(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            reg_result.filename = file.filename
            import_run = svc.process_registry_import(reg_result, file_hash=file_hash)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source_type: {source_type}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return import_run


@router.get("/runs")
def list_import_runs(session: Session = Depends(get_session)):
    runs = session.exec(
        select(ImportRun).order_by(ImportRun.started_at.desc())
    ).all()
    return runs
