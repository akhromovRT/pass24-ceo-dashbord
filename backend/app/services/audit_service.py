"""Хелпер для записи в audit_log.

Пишем `actor_email` снапшотом — чтобы запись пережила удаление пользователя
(actor_user_id уйдёт в NULL по SET NULL, но email останется).
"""
import json

from sqlmodel import Session

from app.models import AuditLog, User


def write_audit(
    session: Session,
    *,
    actor: User | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
    ip: str | None = None,
) -> None:
    """Запись в audit_log. Commit делает caller — мы только добавляем."""
    entry = AuditLog(
        actor_user_id=actor.id if actor else None,
        actor_email=actor.email if actor else None,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=json.dumps(details, ensure_ascii=False) if details else None,
        ip=ip,
    )
    session.add(entry)
