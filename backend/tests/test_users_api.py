import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.core.security import get_password_hash
from app.main import app
from app.models import User, UserRole


def _make_user(role: UserRole, email: str = "u@test.ru", password: str = "InitialPass123") -> User:
    return User(
        name="Test",
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        is_active=True,
    )


@pytest.fixture
def admin_client(db_session: Session):
    admin = _make_user(UserRole.ADMIN, email="admin@test.ru")
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    def override_get_session():
        yield db_session

    def override_admin():
        return admin

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_admin
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def viewer_client(db_session: Session):
    viewer = _make_user(UserRole.VIEWER, email="viewer@test.ru")
    db_session.add(viewer)
    db_session.commit()
    db_session.refresh(viewer)

    def override_get_session():
        yield db_session

    def override_viewer():
        return viewer

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_current_user] = override_viewer
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestUsersAdminOnly:
    def test_viewer_cannot_list_users(self, viewer_client: TestClient):
        r = viewer_client.get("/api/v1/users")
        assert r.status_code == 403

    def test_admin_can_list_users(self, admin_client: TestClient):
        r = admin_client.get("/api/v1/users")
        assert r.status_code == 200
        assert any(u["email"] == "admin@test.ru" for u in r.json())

    def test_admin_creates_user_with_generated_password(self, admin_client: TestClient):
        r = admin_client.post(
            "/api/v1/users",
            json={"name": "Alex", "email": "alex@test.ru", "role": "manager"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "alex@test.ru"
        assert body["role"] == "manager"
        assert body["generated_password"] is not None
        assert len(body["generated_password"]) >= 12

    def test_admin_creates_user_with_explicit_password(self, admin_client: TestClient):
        r = admin_client.post(
            "/api/v1/users",
            json={
                "name": "Bob",
                "email": "bob@test.ru",
                "role": "viewer",
                "password": "ExplicitPass1",
            },
        )
        assert r.status_code == 201
        assert r.json()["generated_password"] is None

    def test_cannot_create_duplicate_email(self, admin_client: TestClient):
        admin_client.post(
            "/api/v1/users",
            json={"name": "A", "email": "dup@test.ru", "role": "viewer"},
        )
        r = admin_client.post(
            "/api/v1/users",
            json={"name": "B", "email": "dup@test.ru", "role": "viewer"},
        )
        assert r.status_code == 409

    def test_admin_resets_password(self, admin_client: TestClient):
        created = admin_client.post(
            "/api/v1/users",
            json={"name": "C", "email": "c@test.ru", "role": "viewer"},
        ).json()
        user_id = created["id"]
        r = admin_client.post(f"/api/v1/users/{user_id}/reset-password")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "c@test.ru"
        assert len(body["new_password"]) >= 12


class TestChangePassword:
    def test_user_changes_own_password(self, viewer_client: TestClient):
        r = viewer_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "InitialPass123", "new_password": "NewPass4567"},
        )
        assert r.status_code == 200, r.text

    def test_wrong_current_password_rejected(self, viewer_client: TestClient):
        r = viewer_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "WRONG", "new_password": "NewPass4567"},
        )
        assert r.status_code == 400

    def test_same_password_rejected(self, viewer_client: TestClient):
        r = viewer_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "InitialPass123", "new_password": "InitialPass123"},
        )
        assert r.status_code == 400

    def test_short_password_rejected(self, viewer_client: TestClient):
        r = viewer_client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "InitialPass123", "new_password": "x"},
        )
        assert r.status_code == 422


class TestMe:
    def test_me_returns_current_user(self, viewer_client: TestClient):
        r = viewer_client.get("/api/v1/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "viewer@test.ru"
        assert body["role"] == "viewer"


class TestUserOptions:
    def test_users_options_available_to_non_admin(self, viewer_client: TestClient):
        resp = viewer_client.get("/api/v1/users/options")
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list)
        assert all("id" in r and "name" in r for r in rows)
