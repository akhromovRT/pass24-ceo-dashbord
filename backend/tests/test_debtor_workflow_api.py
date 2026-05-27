"""API-тесты для /debtor-workflow (статус проработки + комментарий)."""
from datetime import date
from decimal import Decimal
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.database import get_session
from app.main import app
from app.models import (
    DebtorWorkflow, DebtorWorkflowStatus, Organization, OrgStatus, User, UserRole,
)


def _seed_user(db_session: Session) -> User:
    u = User(
        name="Test User", email="t@x", hashed_password="h",
        role=UserRole.ADMIN, is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _seed_org(db_session: Session) -> Organization:
    o = Organization(
        inn="7700000777", name_1c="ООО ВОРКФЛОУ", status=OrgStatus.ACTIVE,
        in_registry=True, total_debt=Decimal("12345"),
    )
    db_session.add(o)
    db_session.commit()
    db_session.refresh(o)
    return o


def _client_with(db_session: Session, user: User) -> TestClient:
    from app.api.v1.auth import get_current_user
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestUpsertWorkflow:
    def test_create_then_update(self, db_session: Session):
        user = _seed_user(db_session)
        org = _seed_org(db_session)
        client = _client_with(db_session, user)
        try:
            # 1) Создание — задаём только статус
            r = client.put(
                f"/api/v1/debtor-workflow/{org.id}",
                json={"status": "in_progress"},
            )
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["status"] == "in_progress"
            assert d["comment"] is None
            assert d["updated_by_id"] == str(user.id)
            assert d["updated_by_name"] == "Test User"

            # 2) Обновление — только комментарий, статус сохраняется
            r = client.put(
                f"/api/v1/debtor-workflow/{org.id}",
                json={"comment": "Ждём оплату по счёту 42"},
            )
            assert r.status_code == 200
            d = r.json()
            assert d["status"] == "in_progress"  # не сбросился
            assert d["comment"] == "Ждём оплату по счёту 42"

            # 3) Полная смена на done
            r = client.put(
                f"/api/v1/debtor-workflow/{org.id}",
                json={"status": "done", "comment": "Оплачено 27.05"},
            )
            assert r.status_code == 200
            d = r.json()
            assert d["status"] == "done"
            assert d["comment"] == "Оплачено 27.05"

            # В БД ровно одна запись
            rows = db_session.query(DebtorWorkflow).all()
            assert len(rows) == 1
            assert rows[0].status == DebtorWorkflowStatus.DONE
        finally:
            app.dependency_overrides.clear()

    def test_empty_payload_rejected(self, db_session: Session):
        user = _seed_user(db_session)
        org = _seed_org(db_session)
        client = _client_with(db_session, user)
        try:
            r = client.put(
                f"/api/v1/debtor-workflow/{org.id}",
                json={},
            )
            assert r.status_code == 400
            assert "at least one" in r.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_404_for_unknown_org(self, db_session: Session):
        user = _seed_user(db_session)
        client = _client_with(db_session, user)
        try:
            r = client.put(
                f"/api/v1/debtor-workflow/{uuid.uuid4()}",
                json={"status": "done"},
            )
            assert r.status_code == 404
        finally:
            app.dependency_overrides.clear()
