import hashlib
import json
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import ImportRun
from app.parser.bank_statement import parse_bank_statement
from app.parser.debt_report import parse_debt_report
from app.parser.payments_report import parse_payments_report
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
    source_type: Literal["debt", "bank", "registry", "payments"] = Query(default="debt"),
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
        elif source_type == "payments":
            try:
                pay_result = parse_payments_report(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            pay_result.filename = file.filename
            import_run = svc.process_payments_report(pay_result, file_hash=file_hash)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown source_type: {source_type}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return import_run



@router.post("/preview")
def preview_import(
    file: UploadFile,
    source_type: Literal["bank", "payments"] = Query(default="bank"),
    session: Session = Depends(get_session),
):
    """Фаза 1: парсим файл, в БД не пишем, возвращаем платежи без периода."""
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    content = file.file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == file_hash)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="File already imported")

    tmp = tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False)
    tmp_path = tmp.name
    try:
        tmp.write(content)
        tmp.close()
        if source_type == "bank":
            result = parse_bank_statement(tmp_path)
        else:
            result = parse_payments_report(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Parse error: {e}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    payments_without_period = []
    total_amount = 0.0
    for idx, p in enumerate(result.payments):
        total_amount += float(p.amount)
        if p.payment_info and p.payment_info.periods:
            detected = {
                "year": p.payment_info.periods[0][0],
                "month": p.payment_info.periods[0][1],
            }
        else:
            detected = None
        if detected is None:
            payments_without_period.append({
                "index": idx,
                "date": str(p.date),
                "amount": float(p.amount),
                "counterparty": p.counterparty,
                "inn": p.inn,
                "description": p.description,
                "detected_period": None,
            })

    return {
        "file_hash": file_hash,
        "source_type": source_type,
        "summary": {
            "total_payments": len(result.payments),
            "total_amount": round(total_amount, 2),
            "without_period": len(payments_without_period),
        },
        "payments": payments_without_period,
    }


@router.post("/commit")
def commit_import(
    file: UploadFile,
    source_type: Literal["bank", "payments"] = Query(default="bank"),
    file_hash: str = Form(...),
    period_overrides_json: str = Form(default="{}"),
    session: Session = Depends(get_session),
):
    """Фаза 2: re-парсим файл, сверяем hash, применяем оверрайды, пишем в БД."""
    if not file.filename or not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(status_code=400, detail="Only .xls/.xlsx files accepted")

    content = file.file.read()
    actual_hash = hashlib.sha256(content).hexdigest()
    if actual_hash != file_hash:
        raise HTTPException(status_code=400, detail="file_hash mismatch — файл изменился")

    existing = session.exec(
        select(ImportRun).where(ImportRun.file_hash == actual_hash)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="File already imported")

    overrides: dict[int, tuple[int, int]] = {}
    try:
        raw = json.loads(period_overrides_json or "{}")
        for k, v in raw.items():
            idx = int(k)
            year, month = int(v["year"]), int(v["month"])
            if not (1 <= month <= 12 and 2010 <= year <= 2035):
                raise HTTPException(status_code=422, detail=f"Invalid period at index {k}")
            overrides[idx] = (year, month)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid period_overrides_json: {exc}")

    tmp = tempfile.NamedTemporaryFile(suffix=Path(file.filename).suffix, delete=False)
    tmp_path = tmp.name
    svc = ImportService(session)
    try:
        tmp.write(content)
        tmp.close()
        if source_type == "bank":
            try:
                bank_result = parse_bank_statement(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            bank_result.filename = file.filename
            import_run = svc.process_bank_import(
                bank_result, file_hash=actual_hash, period_overrides=overrides
            )
        else:
            try:
                pay_result = parse_payments_report(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Parse error: {e}")
            pay_result.filename = file.filename
            import_run = svc.process_payments_report(
                pay_result, file_hash=actual_hash, period_overrides=overrides
            )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return import_run


@router.get("/runs")
def list_import_runs(session: Session = Depends(get_session)):
    runs = session.exec(
        select(ImportRun).order_by(ImportRun.started_at.desc())
    ).all()
    return runs
