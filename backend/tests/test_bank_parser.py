import os
from pathlib import Path

import pytest

from app.parser.bank_statement import extract_payment_info, parse_bank_statement

BANK_STATEMENT_PATH = os.path.expanduser("~/Downloads/Выписка_40702810002630000347_03.03.2026.xlsx")


class TestExtractPaymentInfo:
    def test_extract_invoice_number(self):
        info = extract_payment_info(
            "Счет № 238 от 24.02.2026 г. за доступ на месяц к системе за март 2026 г."
        )
        assert info.invoice_number == "238"

    def test_extract_invoice_bp_prefix(self):
        info = extract_payment_info("ОПЛАТА ПО СЧЕТУ № БП-231 ОТ 24.02.2026 ЗА ДОСТУП К СИСТЕМЕ")
        assert info.invoice_number == "БП-231"

    def test_extract_contract_number(self):
        info = extract_payment_info("ПО ДОГОВОРУ ОКАЗАНИЯ УСЛУГ № ИС/01082018 ОТ 01.08.2018")
        assert info.contract_number == "ИС/01082018"

    def test_extract_contract_number_dashes(self):
        info = extract_payment_info("ПО ДОГОВОРУ №10129-/02/2023 ОТ 20.02.2023Г.")
        assert info.contract_number == "10129-/02/2023"

    def test_extract_period_month_name(self):
        info = extract_payment_info("за доступ за март 2026 г.")
        assert info.period_month == 3
        assert info.period_year == 2026

    def test_extract_period_slash(self):
        info = extract_payment_info("за 03/ 2026Г.")
        assert info.period_month == 3
        assert info.period_year == 2026

    def test_extract_period_in_phrase(self):
        info = extract_payment_info("В ФЕВРАЛЕ 2026Г.")
        assert info.period_month == 2
        assert info.period_year == 2026

    def test_extract_tariff_prof(self):
        info = extract_payment_info("Тариф ПРОФ за март 2026")
        assert info.tariff == "PROF"

    def test_extract_tariff_standart(self):
        info = extract_payment_info("STANDART за март 2026")
        assert info.tariff == "STANDART"

    def test_no_match_returns_nones(self):
        info = extract_payment_info("Просто текст без полезной информации")
        assert info.invoice_number is None
        assert info.contract_number is None
        assert info.period_month is None


@pytest.mark.skipif(
    not Path(BANK_STATEMENT_PATH).exists(),
    reason="Real bank statement file not available",
)
class TestParseBankStatement:
    def test_payments_count(self):
        result = parse_bank_statement(BANK_STATEMENT_PATH)
        assert len(result.payments) >= 20

    def test_all_have_inn_and_amount(self):
        result = parse_bank_statement(BANK_STATEMENT_PATH)
        for p in result.payments:
            assert p.inn, f"Missing INN for {p.counterparty}"
            assert p.amount > 0, f"Zero amount for {p.counterparty}"

    def test_header_parsed(self):
        result = parse_bank_statement(BANK_STATEMENT_PATH)
        assert result.account_number is not None
        assert result.owner is not None

    def test_payment_info_extracted(self):
        result = parse_bank_statement(BANK_STATEMENT_PATH)
        has_invoice = any(p.payment_info.invoice_number for p in result.payments)
        assert has_invoice, "At least some payments should have invoice numbers"
