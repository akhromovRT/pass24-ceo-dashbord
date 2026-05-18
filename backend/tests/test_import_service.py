from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.models import Organization, Contract, Document, ImportRun, Alert
from app.parser.debt_report import (
    ParsedBuyer, ParsedContract, ParsedDocument, ParseResult,
)
from app.services.import_service import ImportService


def _make_parse_result() -> ParseResult:
    doc = ParsedDocument(
        raw_name="Реализация (акт) № 201 от 31.12.2025",
        doc_type="sale",
        doc_number="201",
        doc_date=date(2025, 12, 31),
        amount=Decimal("18000.00"),
        sold=Decimal("18000.00"),
        paid=Decimal("18000.00"),
    )
    contract = ParsedContract(
        raw_name="Договор оказания услуг № 2511/1065/П от 25.11.2020",
        contract_number="2511/1065/П",
        contract_date=date(2020, 11, 25),
        sold=Decimal("18000.00"),
        paid=Decimal("18000.00"),
        documents=[doc],
    )
    buyer = ParsedBuyer(
        name='7 НЕБО ТСН_ДИАДОК',
        inn="9717053891",
        sold=Decimal("18000.00"),
        paid=Decimal("18000.00"),
        contracts=[contract],
    )
    return ParseResult(
        filename="test.xlsx",
        file_hash="a" * 64,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 28),
        total_rows=3,
        buyers_count=1,
        contracts_count=1,
        documents_count=1,
        buyers=[buyer],
    )


class TestImportService:
    def test_process_import_creates_records(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        import_run = svc.process_import(parse_result)

        assert import_run.status.value == "completed"
        assert import_run.buyers_count == 1
        assert import_run.contracts_count == 1
        assert import_run.documents_count == 1

    def test_creates_organization(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)

        org = db_session.exec(
            select(Organization).where(Organization.inn == "9717053891")
        ).first()
        assert org is not None
        assert "7 НЕБО" in org.name_1c

    def test_creates_contract(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)

        contracts = db_session.exec(select(Contract)).all()
        assert len(contracts) == 1
        assert contracts[0].contract_number == "2511/1065/П"

    def test_creates_documents(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)

        docs = db_session.exec(select(Document)).all()
        assert len(docs) == 1
        assert docs[0].doc_number == "201"

    def test_creates_alert_for_new_client(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)

        alerts = db_session.exec(select(Alert)).all()
        assert any(a.alert_type.value == "unassigned_client" for a in alerts)

    def test_idempotent_organization(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)
        svc.process_import(parse_result)

        orgs = db_session.exec(select(Organization)).all()
        assert len(orgs) == 1

    def test_cleans_name(self, db_session: Session):
        parse_result = _make_parse_result()
        svc = ImportService(db_session)
        svc.process_import(parse_result)

        org = db_session.exec(
            select(Organization).where(Organization.inn == "9717053891")
        ).first()
        assert "_ДИАДОК" not in org.name_1c
        assert "_СБИС" not in org.name_1c


def test_bank_import_triggers_ledger_recompute(db_session: Session):
    """После банк-импорта у затронутых клиентов появляются payment_allocation."""
    from app.models import (
        ChargeSource,
        MonthlyCharge,
        OrgStatus,
        PaymentAllocation,
        TariffPeriod,
    )
    from app.parser.bank_statement import BankStatementResult, ParsedPayment, PaymentInfo

    org = Organization(inn="7700000010", name_1c="Бэнк Клиент",
                       status=OrgStatus.ACTIVE, monthly_ap=Decimal("8000"))
    db_session.add(org)
    db_session.flush()
    db_session.add(TariffPeriod(organization_id=org.id, valid_from=date(2026, 1, 1),
                                monthly_amount=Decimal("8000")))
    db_session.add(MonthlyCharge(organization_id=org.id, year=2026, month=1,
                                 amount=Decimal("8000"),
                                 source=ChargeSource.SYNTHETIC_TARIFF))
    db_session.commit()
    result = BankStatementResult(filename="t.xlsx", payments=[
        ParsedPayment(date=date(2026, 1, 15), doc_number="1", amount=Decimal("8000"),
                      counterparty="Бэнк Клиент", inn="7700000010",
                      description="оплата за доступ", payment_info=PaymentInfo()),
    ])
    ImportService(db_session).process_bank_import(result, file_hash="hash-recompute-1")
    allocs = db_session.exec(select(PaymentAllocation)).all()
    assert len(allocs) >= 1
