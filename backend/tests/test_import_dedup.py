"""Idempotency tests: re-importing the same data must not produce duplicates."""
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.models import (
    ClientObject, Contract, Document, DocType, Organization, OrgStatus,
)
from app.parser.bank_statement import (
    BankStatementResult, ParsedPayment, PaymentInfo,
)
from app.parser.registry import (
    ParsedRegistryCompany, ParsedRegistryObject, RegistryParseResult,
)
from app.services.import_service import ImportService


def _payment(d, amount, name="X", inn="1234567890", num="1", desc="", year=None, month=None):
    return ParsedPayment(
        date=d, doc_number=num, amount=Decimal(str(amount)),
        counterparty=name, inn=inn, description=desc,
        doc_type="Платежное поручение",
        payment_info=PaymentInfo(period_year=year, period_month=month),
    )


def _result(payments):
    return BankStatementResult(filename="t.xlsx", account_number="40702",
                               period="period", owner="owner", payments=payments)


class TestBankImportDedup:
    def test_same_payment_in_two_imports_no_dup(self, db_session: Session):
        # First import: 2 payments
        r1 = _result([
            _payment(date(2026, 1, 15), 5000, num="1"),
            _payment(date(2026, 2, 15), 7000, num="2"),
        ])
        run1 = ImportService(db_session).process_bank_import(r1, file_hash="h1")
        assert run1.documents_count == 2

        # Second import: overlapping (payment 2 + new payment 3)
        r2 = _result([
            _payment(date(2026, 2, 15), 7000, num="2"),  # SAME as r1.2
            _payment(date(2026, 3, 15), 9000, num="3"),  # NEW
        ])
        run2 = ImportService(db_session).process_bank_import(r2, file_hash="h2")

        assert run2.documents_count == 1  # only payment 3 added
        assert run2.delta_summary["skipped_duplicate_documents"] == 1
        all_docs = db_session.exec(select(Document).where(Document.doc_type == DocType.PAYMENT)).all()
        assert len(all_docs) == 3  # 2 + 1, not 2 + 2

    def test_re_import_full_file_yields_zero_new(self, db_session: Session):
        r1 = _result([
            _payment(date(2026, 1, 15), 5000, num="1"),
            _payment(date(2026, 2, 15), 7000, num="2"),
        ])
        ImportService(db_session).process_bank_import(r1, file_hash="h1")

        # Re-importing the exact same file again (different hash to bypass endpoint check)
        run2 = ImportService(db_session).process_bank_import(r1, file_hash="h2")

        assert run2.documents_count == 0
        assert run2.delta_summary["skipped_duplicate_documents"] == 2
        all_docs = db_session.exec(select(Document)).all()
        assert len(all_docs) == 2

    def test_payment_with_different_amount_is_not_dup(self, db_session: Session):
        r1 = _result([_payment(date(2026, 1, 15), 5000, num="1")])
        ImportService(db_session).process_bank_import(r1, file_hash="h1")
        r2 = _result([_payment(date(2026, 1, 15), 5001, num="1")])  # different amount
        run2 = ImportService(db_session).process_bank_import(r2, file_hash="h2")
        assert run2.documents_count == 1
        all_docs = db_session.exec(select(Document)).all()
        assert len(all_docs) == 2


class TestRegistryImportDedup:
    def test_re_import_same_company_no_new_objects(self, db_session: Session):
        result = RegistryParseResult(
            filename="t.xlsx",
            companies=[ParsedRegistryCompany(
                inn="1234567890",
                company_name="X",
                objects=[ParsedRegistryObject(name="Obj1", cloud_url="https://a.com")],
            )],
        )
        ImportService(db_session).process_registry_import(result, file_hash="h1")
        objects_after_first = db_session.exec(select(ClientObject)).all()
        assert len(objects_after_first) == 1

        # Re-import — must not add another ClientObject
        run2 = ImportService(db_session).process_registry_import(result, file_hash="h2")
        objects_after_second = db_session.exec(select(ClientObject)).all()
        assert len(objects_after_second) == 1
        assert run2.delta_summary["objects_added"] == 0

    def test_case_insensitive_name_match(self, db_session: Session):
        # First import: 'ЖК Андерсен'
        r1 = RegistryParseResult(filename="t.xlsx", companies=[
            ParsedRegistryCompany(inn="1234567890", company_name="X",
                objects=[ParsedRegistryObject(name="ЖК Андерсен", cloud_url="https://a.com")])
        ])
        ImportService(db_session).process_registry_import(r1, file_hash="h1")

        # Second import: 'жк андерсен' (lowercase) — must match, not duplicate
        r2 = RegistryParseResult(filename="t.xlsx", companies=[
            ParsedRegistryCompany(inn="1234567890", company_name="X",
                objects=[ParsedRegistryObject(name="жк андерсен", cloud_url="https://a.com")])
        ])
        ImportService(db_session).process_registry_import(r2, file_hash="h2")

        objects = db_session.exec(select(ClientObject)).all()
        assert len(objects) == 1


class TestDebtImportDedup:
    def test_buyer_inn_normalized_on_create(self, db_session: Session):
        from app.parser.debt_report import (
            ParsedBuyer, ParsedContract, ParsedDocument, ParseResult,
        )
        # Existing org with normalized INN
        org = Organization(inn="071513837810", name_1c="Existing")
        db_session.add(org); db_session.commit()

        # New debt report comes with INN without leading zero
        result = ParseResult(
            filename="t.xls",
            file_hash="h1",
            period_start=None, period_end=None, total_rows=1,
            buyers=[ParsedBuyer(
                name="X", inn="71513837810",  # 11 digits, missing leading 0
                debt_end=Decimal("100"),
                contracts=[],
            )],
        )
        ImportService(db_session).process_import(result)

        orgs = db_session.exec(select(Organization)).all()
        assert len(orgs) == 1  # NOT 2 — normalized lookup found the existing one
        assert orgs[0].inn == "071513837810"
        assert orgs[0].total_debt == Decimal("100")

    def test_redundant_documents_skipped_on_reimport(self, db_session: Session):
        from app.parser.debt_report import (
            ParsedBuyer, ParsedContract, ParsedDocument, ParseResult,
        )
        def make_result(file_hash):
            return ParseResult(
                filename="t.xls",
                file_hash=file_hash,
                period_start=None, period_end=None, total_rows=1,
                buyers=[ParsedBuyer(
                    name="Y", inn="1234567890",
                    contracts=[ParsedContract(
                        raw_name="Договор № 1",
                        contract_number="1",
                        contract_date=date(2025, 1, 1),
                        documents=[
                            ParsedDocument(
                                raw_name="Реализация № 10",
                                doc_type="sale", doc_number="10",
                                doc_date=date(2025, 6, 30),
                                amount=Decimal("10000"),
                                sold=None, paid=None,
                            ),
                        ],
                    )],
                )],
            )
        ImportService(db_session).process_import(make_result("h1"))
        run2 = ImportService(db_session).process_import(make_result("h2"))

        all_docs = db_session.exec(select(Document)).all()
        assert len(all_docs) == 1
        assert run2.delta_summary["skipped_duplicate_documents"] == 1
