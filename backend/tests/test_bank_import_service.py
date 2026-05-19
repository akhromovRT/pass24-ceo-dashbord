from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.models import Contract, Document, DocType, ImportRun, Organization, OrgStatus
from app.parser.bank_statement import (
    BankStatementResult,
    ParsedPayment,
    PaymentInfo,
)
from app.services.import_service import ImportService


def _make_payment(date_, amount, counterparty, inn, description="", doc_number="1"):
    return ParsedPayment(
        date=date_,
        doc_number=doc_number,
        amount=Decimal(str(amount)),
        counterparty=counterparty,
        inn=inn,
        description=description,
        doc_type="Платежное поручение",
        payment_info=PaymentInfo(period_month=5, period_year=2026),
    )


def _make_result(payments):
    return BankStatementResult(
        filename="test.xlsx",
        account_number="40702",
        period="01.01.2026 - 13.05.2026",
        owner="ОНВИ Сервис",
        payments=payments,
    )


class TestBankImport:
    def test_creates_payment_for_existing_org(self, db_session: Session):
        # Arrange: org exists
        org = Organization(inn="7703746155", name_1c="ОНВИ Сервис")
        db_session.add(org)
        db_session.commit()

        payment = _make_payment(date(2026, 1, 15), 10000, "ОНВИ Сервис", "7703746155")
        result = _make_result([payment])

        # Act
        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc123")

        # Assert
        assert run.documents_count == 1
        assert run.buyers_count == 1
        assert run.new_buyers == 0
        docs = db_session.exec(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].doc_type == DocType.PAYMENT
        assert docs[0].amount == Decimal("10000")
        assert docs[0].organization_id == org.id
        assert docs[0].period_month == 5
        assert docs[0].period_year == 2026

    def test_creates_org_for_new_inn(self, db_session: Session):
        payment = _make_payment(date(2026, 1, 15), 5000, "Новая компания ООО", "1234567890")
        result = _make_result([payment])

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")

        assert run.new_buyers == 1
        orgs = db_session.exec(select(Organization)).all()
        assert len(orgs) == 1
        assert orgs[0].inn == "1234567890"
        assert orgs[0].status == OrgStatus.PROSPECT
        assert orgs[0].name_1c == "Новая компания ООО"

    def test_synthetic_bank_contract_reused(self, db_session: Session):
        # Два платежа от одной новой компании — должен быть ОДИН синтетический контракт
        payments = [
            _make_payment(date(2026, 1, 15), 5000, "Компания", "1234567890"),
            _make_payment(date(2026, 2, 15), 7000, "Компания", "1234567890"),
        ]
        result = _make_result(payments)

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")

        assert run.contracts_count == 1
        assert run.documents_count == 2
        contracts = db_session.exec(select(Contract)).all()
        assert len(contracts) == 1
        assert contracts[0].contract_number == "BANK-IMPORT"

    def test_normalizes_inn_leading_zero(self, db_session: Session):
        # ИНН пришёл из выписки как 9-значный (потеряна leading 0) — должен стать 10-значным
        org = Organization(inn="0123456789", name_1c="Existing")
        db_session.add(org)
        db_session.commit()

        payment = _make_payment(date(2026, 1, 15), 5000, "Existing", "123456789")  # 9 digits
        result = _make_result([payment])

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")

        assert run.new_buyers == 0  # должен сматчиться через normalization
        docs = db_session.exec(select(Document)).all()
        assert docs[0].organization_id == org.id

    def test_skips_payments_without_inn(self, db_session: Session):
        payments = [
            _make_payment(date(2026, 1, 15), 5000, "С ИНН", "1234567890"),
            _make_payment(date(2026, 1, 16), 3000, "Без ИНН", ""),
        ]
        result = _make_result(payments)

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")

        assert run.documents_count == 1
        assert run.delta_summary["skipped_no_inn"] == 1
        assert len(run.errors) == 1
        assert run.errors[0]["type"] == "no_inn"

    def test_invalid_inn_length_recorded(self, db_session: Session):
        # 13-значный ИНН (как Мазуров в Bitrix) — должен быть скипнут с ошибкой
        payment = _make_payment(date(2026, 1, 15), 5000, "Битый ИНН", "1234567890123")
        result = _make_result([payment])

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")

        assert run.documents_count == 0
        assert any(e["type"] == "invalid_inn_length" for e in (run.errors or []))

    def test_strips_payment_info_suffix_in_name(self, db_session: Session):
        # Bank counterparty часто содержит "ООО Х Р/С 40702..." — отсекаем
        payment = _make_payment(
            date(2026, 1, 15), 5000,
            "ООО «КОНТИНЕНТАЛЬ СЕРВИС» Р/С 40702810038170017138 в Сбербанке",
            "7731599248",
        )
        result = _make_result([payment])

        svc = ImportService(db_session)
        svc.process_bank_import(result, file_hash="abc")

        org = db_session.exec(select(Organization).where(Organization.inn == "7731599248")).first()
        assert org is not None
        assert "Р/С" not in org.name_1c
        assert "КОНТИНЕНТАЛЬ" in org.name_1c

    def test_period_extracted_from_payments(self, db_session: Session):
        payments = [
            _make_payment(date(2026, 1, 15), 5000, "X", "1234567890"),
            _make_payment(date(2026, 5, 13), 7000, "X", "1234567890"),
        ]
        result = _make_result(payments)

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")
        assert run.period_start == date(2026, 1, 15)
        assert run.period_end == date(2026, 5, 13)

    def test_delta_summary_includes_metadata(self, db_session: Session):
        payment = _make_payment(date(2026, 1, 15), 5000, "X", "1234567890")
        result = _make_result([payment])

        svc = ImportService(db_session)
        run = svc.process_bank_import(result, file_hash="abc")
        assert run.delta_summary["source"] == "bank_statement"
        assert run.delta_summary["account_number"] == "40702"
        assert run.delta_summary["owner"] == "ОНВИ Сервис"
        assert run.delta_summary["total_payments"] == 1

    def test_period_override_sets_period_manual_true(self, db_session: Session):
        """Оверрайд периода: Document.period_manual=True, period_year/month по оверрайду."""
        payment = ParsedPayment(
            date=date(2026, 5, 18),
            doc_number="542",
            amount=Decimal("12387.38"),
            counterparty='ООО Агростройкомплекс',
            inn="5024039775",
            description="Доступ на месяц 2026г. к системе PASS24.online",
            payment_info=PaymentInfo(),
        )
        result = _make_result([payment])

        svc = ImportService(db_session)
        svc.process_bank_import(
            result,
            file_hash="xyz",
            period_overrides={0: (2026, 5)},
        )

        docs = db_session.exec(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].period_manual is True
        assert docs[0].period_year == 2026
        assert docs[0].period_month == 5

    def test_no_override_period_manual_false(self, db_session: Session):
        """Без оверрайда Document.period_manual остаётся False."""
        payment = _make_payment(date(2026, 5, 6), 12387.38, "X", "5024039775")
        result = _make_result([payment])

        svc = ImportService(db_session)
        svc.process_bank_import(result, file_hash="qqq")

        docs = db_session.exec(select(Document)).all()
        assert docs[0].period_manual is False

    def test_period_override_applies_to_correct_index(self, db_session: Session):
        """Оверрайд по индексу 1 затрагивает только второй платёж, не первый."""
        payments = [
            _make_payment(date(2026, 5, 1), 1000, "A", "1234567890"),
            ParsedPayment(
                date=date(2026, 5, 2),
                doc_number="1",
                amount=Decimal("2000"),
                counterparty="B",
                inn="5024039775",
                description="Доступ к системе PASS24.online",
                payment_info=PaymentInfo(),
            ),
        ]
        result = _make_result(payments)

        svc = ImportService(db_session)
        svc.process_bank_import(
            result, file_hash="idx-test", period_overrides={1: (2026, 4)}
        )

        docs = sorted(db_session.exec(select(Document)).all(), key=lambda d: d.amount)
        assert len(docs) == 2
        assert docs[0].period_manual is False   # индекс 0 не затронут
        assert docs[1].period_manual is True    # индекс 1 — оверрайд
        assert docs[1].period_year == 2026
        assert docs[1].period_month == 4
