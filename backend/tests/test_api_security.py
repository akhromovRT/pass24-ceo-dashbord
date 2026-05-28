"""Контрольный тест: все защищённые data-маршруты требуют авторизацию.

Срабатывает регрессом на инцидент 2026-05-13 (когда GET /organizations
случайно был доступен без токена). Если новый роутер забыл добавить
get_current_user в dependencies — этот тест провалится.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Эндпоинты, которые ДОЛЖНЫ быть открыты без токена (логин, healthcheck).
PUBLIC_PATHS = {
    "/health",
    "/api/v1/auth/login",
    # /docs, /openapi.json и /redoc — открыты только в DEBUG=true.
    "/docs", "/openapi.json", "/redoc",
    "/openapi.yaml",  # не используется, но FastAPI может отдавать
}


def _all_protected_paths() -> list[tuple[str, str]]:
    """Все GET/POST/PUT/PATCH/DELETE маршруты, кроме PUBLIC_PATHS."""
    out: list[tuple[str, str]] = []
    for route in app.routes:
        # APIRoute или WebSocket — только APIRoute с methods
        methods = getattr(route, "methods", None) or set()
        path = getattr(route, "path", "")
        if not methods or not path:
            continue
        if path in PUBLIC_PATHS:
            continue
        for m in methods:
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append((m, path))
    return out


def _materialize_path(path: str) -> str:
    """Подставляем минимальные dummy-значения в path-параметры."""
    return (
        path
        .replace("{snapshot_id}", "00000000-0000-0000-0000-000000000000")
        .replace("{organization_id}", "00000000-0000-0000-0000-000000000000")
        .replace("{template_id}", "00000000-0000-0000-0000-000000000000")
        .replace("{report_type}", "debtors")
        .replace("{inn}", "0000000000")
        .replace("{id}", "0")
    )


def test_all_protected_routes_reject_anonymous():
    """Без токена все защищённые маршруты должны вернуть 401 или 403."""
    failures: list[str] = []
    for method, path in _all_protected_paths():
        url = _materialize_path(path)
        resp = client.request(method, url)
        if resp.status_code not in (401, 403):
            failures.append(
                f"{method} {url} → {resp.status_code} (ожидали 401/403)"
            )
    assert not failures, (
        "Незащищённые маршруты (или возвращают не-401/403 без токена):\n  - "
        + "\n  - ".join(failures)
    )
