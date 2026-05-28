import os
from datetime import date
from pathlib import Path

import pytest

from app.parser.debt_report import HierarchyLevel, detect_level, parse_debt_report

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

    # --- Новые случаи, исправленные в этапе 1 фикса парсера ---

    def test_group_marker(self):
        # <...> — служебный маркер раскрытия группы 1С, не должен быть ошибкой.
        assert detect_level("<...>", "") == HierarchyLevel.GROUP_MARKER

    def test_correction_dolga_is_document(self):
        assert (
            detect_level("Корректировка долга № 112 от 31.12.2025", "") == HierarchyLevel.DOCUMENT
        )

    def test_correction_realizacii_is_document(self):
        assert (
            detect_level("Корректировка реализации № 2 от 01.10.2025", "")
            == HierarchyLevel.DOCUMENT
        )

    def test_dopsoglashenie_with_dot_and_space(self):
        # Все варианты написания «Доп. согл.», «Доп.согл.», «Доп сог.» → CONTRACT.
        for s in [
            "Доп. согл. № 2 от 22.07.2025 к Дог №10176-/08/2023 от 01.08.2023",
            "Доп.согл. № 1 от 26.05.2025 к Договору №10260-/07/2024 от ...",
            "Доп согл № 1 от 25.06.2025 к дог. №10360-/04/2025 от 29.04.2025",
            "Доп сог. № 3 от 15.07.2025 к Дог № 2021/01-1034/П от 15.07.2021",
        ]:
            assert detect_level(s, "") == HierarchyLevel.CONTRACT, s

    def test_bare_contract_with_letter_prefix(self):
        # «0ББП-000045 от 28.03.2023», «Альфа 2021/05-1089/П от 01.07.2021».
        assert detect_level("0ББП-000045 от 28.03.2023", "") == HierarchyLevel.CONTRACT
        assert detect_level("Альфа 2021/05-1089/П от 01.07.2021", "") == HierarchyLevel.CONTRACT

    def test_bare_contract_with_hash(self):
        # «№2025/01-1007/Р от 18.02.2025», «№ 24/02 - 2025 от 25.02.2025».
        assert detect_level("№2025/01-1007/Р от 18.02.2025 г.", "") == HierarchyLevel.CONTRACT
        assert detect_level("№ 24/02 - 2025 от 25.02.2025", "") == HierarchyLevel.CONTRACT

    def test_contract_without_date(self):
        # «№2021/03-1055/СКУД» — номер без «от <дата>».
        assert detect_level("№2021/03-1055/СКУД", "") == HierarchyLevel.CONTRACT

    def test_contract_contains_dogovor_word(self):
        # Слово «договор» внутри строки (не только в начале).
        assert (
            detect_level(
                "ГРАЖДАНСКО-ПРАВОВОЙ ДОГОВОР (Контракт) № 18-ЗК-24-ХТ СМП от 26.01.2024",
                "",
            )
            == HierarchyLevel.CONTRACT
        )

    def test_schet_with_lowercase(self):
        # Префиксы CONTRACT теперь сравниваются case-insensitive.
        assert detect_level("счет-оферта № 000117 от 28.08.2023", "") == HierarchyLevel.CONTRACT

    def test_bez_dogovora_is_contract(self):
        # «Без договора» — служебный плейсхолдер 1С для документов без привязки.
        assert detect_level("Без договора", "") == HierarchyLevel.CONTRACT

    def test_individual_without_inn_is_buyer(self):
        # Физлицо без ИНН в колонке B — распознаётся по «голому» ФИО.
        for name in [
            "АФАНАСЬЕВ ЮРИЙ ЮРЬЕВИЧ",
            "Карташев Александр Владимирович",
            "КАШИН СТАНИСЛАВ ВЛАДИМИРОВИЧ ФЛ _ почта",
        ]:
            assert detect_level(name, "") == HierarchyLevel.BUYER, name


class TestPeriodParser:
    # Новый формат с датами «за 01.01.2025 - 24.05.2026» (этап 1).
    def test_period_with_dates(self):
        from datetime import date as _date

        from app.parser.debt_report import _parse_period

        s, e = _parse_period("Задолженность покупателей за 01.01.2025 - 24.05.2026 ООО ...")
        assert s == _date(2025, 1, 1)
        assert e == _date(2026, 5, 24)

    def test_period_with_months_backwards_compat(self):
        # Старый формат с русскими месяцами по-прежнему работает.
        from datetime import date as _date

        from app.parser.debt_report import _parse_period

        s, e = _parse_period("Задолженность покупателей за январь 2026 г. - февраль 2026 г.")
        assert s == _date(2026, 1, 1)
        assert e == _date(2026, 2, 28)


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
