from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.main import app
from app.models import Organization, OrgStatus, User, UserRole


@pytest.fixture
def client(db_session: Session):
    def override_get_session():
        yield db_session

    def override_get_current_user():
        return User(
            name="Test",
            email="test@example.com",
            hashed_password="x",
            role=UserRole.ADMIN,
            is_active=True,
        )

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def sample_org(db_session: Session) -> Organization:
    org = Organization(
        inn="9717053891",
        name_1c='ТСН "7 НЕБО"',
        name_display="7 НЕБО",
        status=OrgStatus.ACTIVE,
        monthly_ap=Decimal("15000.00"),
        total_debt=Decimal("20790.00"),
    )
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


class TestOrganizationsAPI:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/organizations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_with_data(self, client: TestClient, sample_org: Organization):
        resp = client.get("/api/v1/organizations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["inn"] == "9717053891"

    def test_search_by_name(self, client: TestClient, sample_org: Organization):
        resp = client.get("/api/v1/organizations?search=НЕБО")
        data = resp.json()
        assert data["total"] == 1

    def test_search_no_match(self, client: TestClient, sample_org: Organization):
        resp = client.get("/api/v1/organizations?search=NONEXISTENT")
        data = resp.json()
        assert data["total"] == 0

    def test_get_by_inn(self, client: TestClient, sample_org: Organization):
        resp = client.get("/api/v1/organizations/9717053891")
        assert resp.status_code == 200
        assert resp.json()["name_display"] == "7 НЕБО"

    def test_get_not_found(self, client: TestClient):
        resp = client.get("/api/v1/organizations/0000000000")
        assert resp.status_code == 404

    def test_pagination(self, client: TestClient, db_session: Session):
        for i in range(5):
            db_session.add(Organization(inn=f"123456789{i}", name_1c=f"Org {i}"))
        db_session.commit()
        resp = client.get("/api/v1/organizations?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
