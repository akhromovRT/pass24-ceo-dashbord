import os
import re
from datetime import date
from pathlib import Path

import pytest

from app.parser.debt_report import detect_level, parse_debt_report, HierarchyLevel

DEBT_REPORT_PATH = os.path.expanduser(
    "~/Downloads/_Spreadsheets/"
    "Задолженность покупателей за Январь 2026 г. - Февраль 2026 г. "
    "ООО  ОНВИ СЕРВИС v.2 на 02.03.2026 г..xls.xlsx"
)


class TestDetectLevel:
    def test_buyer_by_10_digit_inn(self):
        level = detect_level('ООО "7 НЕБО"', "9717053891")
        assert level == HierarchyLevel.BUYER

    def test_buyer_by_12_digit_inn(self):
        level = detect_level("ИП Иванов", "123456789012")
        assert level == HierarchyLevel.BUYER

    def test_contract_dogovor(self):
        level = detect_level("Договор №123 от 01.01.2025", "")
        assert level == HierarchyLevel.CONTRACT

    def test_contract_osnovnoy(self):
        level = detect_level("Основной договор №45", "")
        assert level == HierarchyLevel.CONTRACT

    def test_document_realizatsiya(self):
        level = detect_level("Реализация (акт) 00000001 от 31.01.2026", "")
        assert level == HierarchyLevel.DOCUMENT

    def test_document_postuplenie(self):
        level = detect_level("Поступление на расчетный счет 123 от 15.02.2026", "")
        assert level == HierarchyLevel.DOCUMENT

    def test_total_row(self):
        level = detect_level("Итого", "")
        assert level == HierarchyLevel.TOTAL

    def test_unknown_for_empty(self):
        level = detect_level("", "")
        assert level == HierarchyLevel.UNKNOWN

    def test_not_buyer_with_short_inn(self):
        level = detect_level("Something", "123")
        assert level != HierarchyLevel.BUYER


@pytest.mark.skipif(
    not Path(DEBT_REPORT_PATH).exists(),
    reason="Real debt report file not available",
)
class TestParseDebtReport:
    def test_total_counts(self):
        result = parse_debt_report(DEBT_REPORT_PATH)
        assert result.total_rows > 1500
        assert result.buyers_count >= 240
        assert result.contracts_count >= 200
        assert result.documents_count >= 1000

    def test_period_detection(self):
        result = parse_debt_report(DEBT_REPORT_PATH)
        assert result.period_start == date(2026, 1, 1)
        assert result.period_end == date(2026, 2, 28)

    def test_first_buyer(self):
        result = parse_debt_report(DEBT_REPORT_PATH)
        first = result.buyers[0]
        assert first.inn == "9717053891"
        assert "7 НЕБО" in first.name
        assert len(first.contracts) >= 1
        assert len(first.contracts[0].documents) >= 1

    def test_file_hash(self):
        result = parse_debt_report(DEBT_REPORT_PATH)
        assert len(result.file_hash) == 64

    def test_documents_have_types(self):
        result = parse_debt_report(DEBT_REPORT_PATH)
        first_contract = result.buyers[0].contracts[0]
        for doc in first_contract.documents:
            assert doc.doc_type in ("sale", "payment")
