import re
import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user, require_admin
from app.core.database import get_session
from app.core.security import get_password_hash
from app.models import User, UserRole
from app.services.audit_service import write_audit

router = APIRouter(
    prefix="/users",
    tags=["users"],
)

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class CreateUserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    role: UserRole = UserRole.VIEWER
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_format(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v.lower().strip()


def _serialize(user: User) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("/options", dependencies=[Depends(get_current_user)])
def list_user_options(session: Session = Depends(get_session)):
    users = session.exec(
        select(User).where(User.is_active == True)  # noqa: E712
    ).all()
    return [{"id": str(u.id), "name": u.name} for u in users]


@router.get("", dependencies=[Depends(require_admin)])
def list_users(session: Session = Depends(get_session)):
    users = session.exec(select(User).order_by(User.created_at)).all()
    return [_serialize(u) for u in users]


@router.post("", status_code=201)
def create_user(
    body: CreateUserRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    existing = session.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")

    generated = body.password is None
    password = body.password or _generate_password()
    user = User(
        name=body.name,
        email=body.email,
        role=body.role,
        hashed_password=get_password_hash(password),
        is_active=True,
        # Сгенерированный пароль показывается admin'у один раз — заставляем
        # пользователя сменить его при первом логине. Если admin задал
        # пароль явно — флаг не ставим (admin отвечает за качество).
        must_change_password=generated,
    )
    session.add(user)
    session.flush()
    write_audit(
        session, actor=admin, action="user.create",
        target_type="user", target_id=str(user.id),
        details={"email": user.email, "role": user.role.value,
                 "password_generated": generated},
    )
    session.commit()
    session.refresh(user)
    result = _serialize(user)
    result["generated_password"] = password if generated else None
    return result


class ResetPasswordResponse(BaseModel):
    user_id: str
    email: str
    new_password: str


@router.post("/{user_id}/reset-password")
def reset_password(
    user_id: uuid.UUID,
    session: Session = Depends(get_session),
    admin: User = Depends(require_admin),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    new_password = _generate_password()
    user.hashed_password = get_password_hash(new_password)
    # При сбросе admin'ом — снова требуем сменить пароль на первом логине.
    user.must_change_password = True
    session.add(user)
    write_audit(
        session, actor=admin, action="user.reset_password",
        target_type="user", target_id=str(user.id),
        details={"email": user.email},
    )
    session.commit()
    return ResetPasswordResponse(
        user_id=str(user.id),
        email=user.email,
        new_password=new_password,
    )
