"""API-тесты для /debt-snapshots (этап 3 UI «1С-вид»)."""
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.database import get_session
from app.main import app
from app.models import (
    DebtorWorkflow, DebtorWorkflowStatus, DebtSnapshot, DebtSnapshotLevel,
    DebtSnapshotRow, Organization, OrgStatus,
)
from app.parser.debt_report import (
    ParsedBuyer, ParsedContract, ParsedDocument, ParseResult,
)
from app.services.import_service import ImportService


# Тест-фикстура: подменяем auth-зависимость и сессию.
def _auth_user_stub():
    class _U:
        id = "00000000-0000-0000-0000-000000000001"
        email = "test@x"
        role = "admin"
    return _U()


def _client_with_session(db_session: Session) -> TestClient:
    from app.api.v1.auth import get_current_user
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = _auth_user_stub
    return TestClient(app)


def _seed(db_session: Session) -> str:
    doc = ParsedDocument(
        raw_name="Реализация № 1 от 15.01.2026",
        doc_type="sale", doc_number="1", doc_date=date(2026, 1, 15),
        amount=Decimal("10000"), sold=Decimal("10000"), paid=Decimal("10000"),
    )
    contract = ParsedContract(
        raw_name="Договор № 100 от 01.01.2025",
        contract_number="100", contract_date=date(2025, 1, 1),
        sold=Decimal("10000"), paid=Decimal("10000"),
        debt_end=Decimal("0"), advance_end=Decimal("2000"),
        documents=[doc],
    )
    buyer = ParsedBuyer(
        name="ООО ТЕСТ", inn="7700000001",
        debt_start=Decimal("3000"), sold=Decimal("10000"), paid=Decimal("10000"),
        debt_end=Decimal("0"), advance_end=Decimal("2000"),
        contracts=[contract],
    )
    pr = ParseResult(
        filename="test.xlsx", file_hash="c" * 64,
        period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
        total_rows=3, buyers_count=1, contracts_count=1, documents_count=1,
        buyers=[buyer],
    )
    svc = ImportService(db_session)
    run = svc.process_import(pr)
    return str(run.id)


class TestListSnapshots:
    def test_list_returns_snapshot(self, db_session: Session):
        _seed(db_session)
        client = _client_with_session(db_session)
        r = client.get("/api/v1/debt-snapshots")
        try:
            assert r.status_code == 200
            d = r.json()
            assert len(d) == 1
            assert d[0]["filename"] == "test.xlsx"
            assert d[0]["buyers_count"] == 1
            assert d[0]["total_debt_end"] == 0.0
            assert d[0]["total_advance_end"] == 2000.0
        finally:
            app.dependency_overrides.clear()


class TestLatestSnapshot:
    def test_latest_includes_rows_and_diffs(self, db_session: Session):
        _seed(db_session)
        client = _client_with_session(db_session)
        r = client.get("/api/v1/debt-snapshots/latest")
        try:
            assert r.status_code == 200
            d = r.json()
            assert d["snapshot"]["filename"] == "test.xlsx"
            # 1 buyer + 1 contract + 1 document = 3 строки
            assert len(d["rows"]) == 3
            levels = [row["level"] for row in d["rows"]]
            assert levels == ["buyer", "contract", "document"]
            # Buyer связан с Organization → есть в actual_org_totals
            buyer_row = d["rows"][0]
            assert buyer_row["organization_id"] is not None
            assert buyer_row["organization_id"] in d["actual_org_totals"]
            # Расхождений быть не должно: импорт сам обновил total_debt = debt_end
            assert d["diffs"] == []
        finally:
            app.dependency_overrides.clear()

    def test_404_when_no_snapshots(self, db_session: Session):
        client = _client_with_session(db_session)
        try:
            r = client.get("/api/v1/debt-snapshots/latest")
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()


class TestDiffDetection:
    def test_diff_when_db_total_debt_diverges(self, db_session: Session):
        _seed(db_session)
        # Симулируем дрейф: вручную меняем Organization.total_debt после импорта.
        org = db_session.query(Organization).filter(
            Organization.inn == "7700000001"
        ).one()
        org.total_debt = Decimal("12345.67")
        db_session.add(org)
        db_session.commit()

        client = _client_with_session(db_session)
        try:
            r = client.get("/api/v1/debt-snapshots/latest")
            assert r.status_code == 200
            d = r.json()
            assert len(d["diffs"]) == 1
            diff = d["diffs"][0]
            assert diff["inn"] == "7700000001"
            assert diff["file_debt_end"] == 0.0
            assert diff["db_total_debt"] == 12345.67
            assert diff["delta"] == -12345.67
        finally:
            app.dependency_overrides.clear()


class TestWorkflowInResponse:
    def test_workflow_attached_to_buyer(self, db_session: Session):
        _seed(db_session)
        # Засеваем workflow для нашего ЮЛ.
        org = db_session.query(Organization).filter(
            Organization.inn == "7700000001"
        ).one()
        db_session.add(DebtorWorkflow(
            organization_id=org.id,
            status=DebtorWorkflowStatus.IN_PROGRESS,
            comment="Звонил 27.05, обещают оплату",
        ))
        db_session.commit()

        client = _client_with_session(db_session)
        try:
            r = client.get("/api/v1/debt-snapshots/latest")
            assert r.status_code == 200
            d = r.json()
            wf_map = d["workflow_by_org"]
            assert str(org.id) in wf_map
            entry = wf_map[str(org.id)]
            assert entry["status"] == "in_progress"
            assert entry["comment"] == "Звонил 27.05, обещают оплату"
        finally:
            app.dependency_overrides.clear()


def _mark_in_registry(db_session: Session, inn: str) -> Organization:
    """Импорт-сервис не ставит in_registry автоматически, а only_regular
    требует его. Помечаем вручную для тестов фильтра."""
    org = db_session.query(Organization).filter(Organization.inn == inn).one()
    org.in_registry = True
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


class TestOnlyRegularFilter:
    def test_filter_drops_transit_buyers(self, db_session: Session):
        _seed(db_session)
        # Делаем нашего единственного buyer'а транзитом — он должен
        # отфильтроваться при only_regular=true, и список rows станет пустым.
        org = _mark_in_registry(db_session, "7700000001")
        org.status = OrgStatus.TRANSIT
        db_session.add(org)
        db_session.commit()

        client = _client_with_session(db_session)
        try:
            # Без фильтра — все 3 строки на месте.
            r = client.get("/api/v1/debt-snapshots/latest")
            assert len(r.json()["rows"]) == 3

            # С фильтром — пусто, buyer выбит, дети тоже.
            r = client.get(
                "/api/v1/debt-snapshots/latest",
                params={"only_regular": "true"},
            )
            assert r.status_code == 200
            d = r.json()
            assert d["only_regular"] is True
            assert d["rows"] == []
        finally:
            app.dependency_overrides.clear()

    def test_active_buyer_keeps_children(self, db_session: Session):
        _seed(db_session)
        _mark_in_registry(db_session, "7700000001")
        # buyer active + in_registry, проверяем что only_regular его пропускает
        # вместе с детьми (contract + document).
        client = _client_with_session(db_session)
        try:
            r = client.get(
                "/api/v1/debt-snapshots/latest",
                params={"only_regular": "true"},
            )
            assert r.status_code == 200
            d = r.json()
            assert d["only_regular"] is True
            levels = [row["level"] for row in d["rows"]]
            assert levels == ["buyer", "contract", "document"]
        finally:
            app.dependency_overrides.clear()
