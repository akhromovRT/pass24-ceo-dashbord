"""Парсер реестра «Оплата от покупателей» из 1С — полная история платежей.

Плоский список: одна строка = один входящий платёж. Колонки:
2=Номер, 3=Дата, 4=Поступление, 6=Контрагент, 7=ИНН, 8=Договор,
11=Назначение платежа. Заголовок — строка 1, данные — со строки 2.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.parser.bank_statement import (
    BankStatementResult,
    ParsedPayment,
    extract_payment_info,
)
from app.parser.period_extraction import extract_periods
from app.parser.utils import load_workbook_any


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            parts = value.strip().split(".")
            return date(int(parts[2]), int(parts[1]), int(parts[0]))
        except (ValueError, IndexError):
            return None
    return None


def parse_payments_report(file_path: str | Path) -> BankStatementResult:
    """Парсит файл «Оплата от покупателей» (.xls/.xlsx) → BankStatementResult."""
    file_path = Path(file_path)
    wb = load_workbook_any(file_path)
    ws = wb.active
    result = BankStatementResult(filename=file_path.name)

    for row_idx in range(2, ws.max_row + 1):
        parsed_date = _parse_date(ws.cell(row=row_idx, column=3).value)
        if parsed_date is None:
            continue

        credit = ws.cell(row=row_idx, column=4).value
        if credit in (None, 0, ""):
            continue
        try:
            amount = Decimal(str(credit))
        except (InvalidOperation, ValueError):
            continue
        if amount <= 0:
            continue

        doc_number = str(ws.cell(row=row_idx, column=2).value or "").strip()
        counterparty = str(ws.cell(row=row_idx, column=6).value or "").strip()
        inn = str(ws.cell(row=row_idx, column=7).value or "").strip()
        description = str(ws.cell(row=row_idx, column=11).value or "").strip()

        info = extract_payment_info(description)
        ep = extract_periods(description, parsed_date)
        info.periods = ep.periods
        info.coverage_months = ep.coverage_months
        info.payment_kind = ep.payment_kind
        if ep.periods:
            info.period_year, info.period_month = ep.periods[0]

        result.payments.append(ParsedPayment(
            date=parsed_date,
            doc_number=doc_number,
            amount=amount,
            counterparty=counterparty,
            inn=inn,
            description=description,
            payment_info=info,
        ))

    wb.close()
    return result
