"""Тесты на сохранение полного среза 1С в DebtSnapshot/DebtSnapshotRow (этап 2)."""

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.models import (
    DebtSnapshot,
    DebtSnapshotLevel,
    DebtSnapshotRow,
    Organization,
)
from app.parser.debt_report import (
    ParsedBuyer,
    ParsedContract,
    ParsedDocument,
    ParseResult,
)
from app.services.import_service import ImportService


def _make_parse_result_with_advance() -> ParseResult:
    doc1 = ParsedDocument(
        raw_name="Реализация (акт) № 1 от 15.01.2026",
        doc_type="sale",
        doc_number="1",
        doc_date=date(2026, 1, 15),
        amount=Decimal("10000.00"),
        sold=Decimal("10000.00"),
        paid=Decimal("10000.00"),
    )
    doc2 = ParsedDocument(
        raw_name="Корректировка долга № 5 от 31.01.2026",
        doc_type="correction",
        doc_number="5",
        doc_date=date(2026, 1, 31),
        prepay_in=Decimal("500.00"),
        prepay_used=Decimal("500.00"),
    )
    contract = ParsedContract(
        raw_name="Договор № 100 от 01.01.2025",
        contract_number="100",
        contract_date=date(2025, 1, 1),
        sold=Decimal("10000.00"),
        paid=Decimal("10000.00"),
        prepay_in=Decimal("500.00"),
        prepay_used=Decimal("500.00"),
        debt_end=Decimal("0.00"),
        advance_end=Decimal("2000.00"),
        documents=[doc1, doc2],
    )
    buyer_yul = ParsedBuyer(
        name="ООО ТЕСТ",
        inn="7700000001",
        debt_start=Decimal("3000.00"),
        sold=Decimal("10000.00"),
        paid=Decimal("10000.00"),
        prepay_in=Decimal("500.00"),
        prepay_used=Decimal("500.00"),
        debt_end=Decimal("0.00"),
        advance_end=Decimal("2000.00"),
        contracts=[contract],
    )
    doc_fl = ParsedDocument(
        raw_name="Реализация (акт) № 2 от 20.02.2026",
        doc_type="sale",
        doc_number="2",
        doc_date=date(2026, 2, 20),
        amount=Decimal("5000.00"),
        sold=Decimal("5000.00"),
        debt_end=Decimal("5000.00"),
    )
    contract_fl = ParsedContract(
        raw_name="Без договора",
        sold=Decimal("5000.00"),
        debt_end=Decimal("5000.00"),
        documents=[doc_fl],
    )
    buyer_fl = ParsedBuyer(
        name="ИВАНОВ ИВАН ИВАНОВИЧ",
        inn="",
        sold=Decimal("5000.00"),
        debt_end=Decimal("5000.00"),
        contracts=[contract_fl],
    )

    return ParseResult(
        filename="snapshot-test.xlsx",
        file_hash="b" * 64,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 2, 28),
        total_rows=6,
        buyers_count=2,
        contracts_count=2,
        documents_count=3,
        buyers=[buyer_yul, buyer_fl],
    )


class TestDebtSnapshotCreated:
    def test_snapshot_attached_to_import_run(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        assert snap.filename == "snapshot-test.xlsx"
        assert snap.period_start == date(2026, 1, 1)
        assert snap.period_end == date(2026, 2, 28)
        assert snap.buyers_count == 2
        assert snap.contracts_count == 2
        assert snap.documents_count == 3
        assert snap.buyers_no_inn_count == 1

    def test_totals_aggregated(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        assert snap.total_debt_start == Decimal("3000.00")
        assert snap.total_debt_end == Decimal("5000.00")
        assert snap.total_sold == Decimal("15000.00")
        assert snap.total_advance_end == Decimal("2000.00")
        assert snap.total_prepay_in == Decimal("500.00")

    def test_row_hierarchy_and_fk(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        rows = db_session.exec(
            select(DebtSnapshotRow)
            .where(DebtSnapshotRow.snapshot_id == snap.id)
            .order_by(DebtSnapshotRow.row_index)
        ).all()
        assert len(rows) == 7
        levels = [r.level for r in rows]
        assert levels[0] == DebtSnapshotLevel.BUYER
        assert levels[1] == DebtSnapshotLevel.CONTRACT
        assert levels[2] == DebtSnapshotLevel.DOCUMENT
        assert levels[3] == DebtSnapshotLevel.DOCUMENT
        assert levels[4] == DebtSnapshotLevel.BUYER

        buyer_yul_row, contract_yul_row, doc1, doc2, buyer_fl_row, contract_fl_row, doc_fl = rows
        assert buyer_yul_row.parent_row_id is None
        assert contract_yul_row.parent_row_id == buyer_yul_row.id
        assert doc1.parent_row_id == contract_yul_row.id
        assert doc2.parent_row_id == contract_yul_row.id
        assert buyer_fl_row.parent_row_id is None
        assert contract_fl_row.parent_row_id == buyer_fl_row.id
        assert doc_fl.parent_row_id == contract_fl_row.id

    def test_yul_linked_to_organization(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        yul_rows = db_session.exec(
            select(DebtSnapshotRow)
            .where(DebtSnapshotRow.snapshot_id == snap.id)
            .where(DebtSnapshotRow.organization_id.is_not(None))
        ).all()
        assert len(yul_rows) == 4
        org = db_session.exec(select(Organization).where(Organization.inn == "7700000001")).one()
        for r in yul_rows:
            assert r.organization_id == org.id
        fl_rows = db_session.exec(
            select(DebtSnapshotRow)
            .where(DebtSnapshotRow.snapshot_id == snap.id)
            .where(DebtSnapshotRow.organization_id.is_(None))
        ).all()
        assert len(fl_rows) == 3

    def test_correction_carries_prepay_fields(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        correction = db_session.exec(
            select(DebtSnapshotRow)
            .where(DebtSnapshotRow.snapshot_id == snap.id)
            .where(DebtSnapshotRow.doc_type == "correction")
        ).one()
        assert correction.prepay_in == Decimal("500.00")
        assert correction.prepay_used == Decimal("500.00")
        assert correction.doc_number == "5"

    def test_buyer_row_carries_advance_end(self, db_session: Session):
        svc = ImportService(db_session)
        run = svc.process_import(_make_parse_result_with_advance())
        snap = db_session.exec(
            select(DebtSnapshot).where(DebtSnapshot.import_run_id == run.id)
        ).one()
        buyer_yul = db_session.exec(
            select(DebtSnapshotRow)
            .where(DebtSnapshotRow.snapshot_id == snap.id)
            .where(DebtSnapshotRow.level == DebtSnapshotLevel.BUYER)
            .where(DebtSnapshotRow.raw_inn == "7700000001")
        ).one()
        assert buyer_yul.advance_end == Decimal("2000.00")
        assert buyer_yul.prepay_in == Decimal("500.00")
        assert buyer_yul.prepay_used == Decimal("500.00")
