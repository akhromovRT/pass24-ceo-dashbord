from decimal import Decimal

import openpyxl

from app.parser.payments_report import parse_payments_report

_HEADER = ["Есть файлы", "Номер", "Дата", "Поступление", "Списание", "Контрагент",
           "ИНН", "Договор", "Вх.номер", "Вх.дата", "Назначение платежа",
           "Вид операции"]


def _make_file(tmp_path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(_HEADER)
    for r in rows:
        ws.append(r)
    path = tmp_path / "payments.xlsx"
    wb.save(path)
    return str(path)


def test_parse_payments_report_basic(tmp_path):
    path = _make_file(tmp_path, [
        ["Нет", "00БП-1", "15.03.2026", 12100.0, None, "ООО Ромашка", "7700000001",
         "Договор №1", "5", "15.03.2026", "Оплата за доступ за март 2026",
         "Оплата от покупателя"],
    ])
    result = parse_payments_report(path)
    assert len(result.payments) == 1
    p = result.payments[0]
    assert p.amount == Decimal("12100.0")
    assert p.inn == "7700000001"
    assert p.doc_number == "00БП-1"
    assert p.payment_info.periods == [(2026, 3)]


def test_parse_skips_empty_amount(tmp_path):
    path = _make_file(tmp_path, [
        ["Нет", "00БП-2", "16.03.2026", None, None, "ООО Тест", "7700000002",
         "Договор", "6", "16.03.2026", "оплата", "Оплата от покупателя"],
    ])
    result = parse_payments_report(path)
    assert result.payments == []
