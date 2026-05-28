"""CEO24 — CLI для управления пользователями.

Использование внутри docker-контейнера backend:

    docker exec -it $(docker ps -qf name=backend) \
        python -m scripts.manage_users list

    docker exec -it $(docker ps -qf name=backend) \
        python -m scripts.manage_users create --email a@b.ru --name Alex --role admin

    docker exec -it $(docker ps -qf name=backend) \
        python -m scripts.manage_users reset-password --email a@b.ru

    docker exec -it $(docker ps -qf name=backend) \
        python -m scripts.manage_users set-role --email a@b.ru --role manager

    docker exec -it $(docker ps -qf name=backend) \
        python -m scripts.manage_users deactivate --email a@b.ru

Запуск через `python scripts/manage_users.py ...` тоже поддерживается —
PYTHONPATH добавляется автоматически.
"""

from __future__ import annotations

import os
import sys

# Make `app` importable when this script is invoked as a file (e.g. /app/scripts/manage_users.py).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import argparse
import secrets
import string

from sqlmodel import Session, select

from app.core.database import engine
from app.core.security import get_password_hash
from app.models import User, UserRole


def _generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def cmd_list(_args: argparse.Namespace) -> int:
    with Session(engine) as session:
        users = session.exec(select(User).order_by(User.created_at)).all()
    if not users:
        print("(no users)")
        return 0
    print(f"{'EMAIL':40s} {'ROLE':10s} {'ACTIVE':7s} {'NAME':30s}")
    for u in users:
        print(f"{u.email:40s} {u.role.value:10s} {str(u.is_active):7s} {u.name:30s}")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    role = UserRole(args.role)
    password = args.password or _generate_password()
    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == args.email)).first()
        if existing:
            print(f"ERROR: user {args.email} already exists", file=sys.stderr)
            return 2
        user = User(
            name=args.name,
            email=args.email,
            role=role,
            hashed_password=get_password_hash(password),
            is_active=True,
        )
        session.add(user)
        session.commit()
    print(f"OK created: {args.email} / role={role.value}")
    print(f"PASSWORD: {password}")
    return 0


def cmd_reset_password(args: argparse.Namespace) -> int:
    new_password = args.password or _generate_password()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if not user:
            print(f"ERROR: user {args.email} not found", file=sys.stderr)
            return 2
        user.hashed_password = get_password_hash(new_password)
        session.add(user)
        session.commit()
    print(f"OK reset: {args.email}")
    print(f"PASSWORD: {new_password}")
    return 0


def cmd_set_role(args: argparse.Namespace) -> int:
    role = UserRole(args.role)
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if not user:
            print(f"ERROR: user {args.email} not found", file=sys.stderr)
            return 2
        user.role = role
        session.add(user)
        session.commit()
    print(f"OK {args.email} role -> {role.value}")
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if not user:
            print(f"ERROR: user {args.email} not found", file=sys.stderr)
            return 2
        user.is_active = False
        session.add(user)
        session.commit()
    print(f"OK {args.email} deactivated")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if not user:
            print(f"ERROR: user {args.email} not found", file=sys.stderr)
            return 2
        user.is_active = True
        session.add(user)
        session.commit()
    print(f"OK {args.email} activated")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="CEO24 user management CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List all users")

    c = sub.add_parser("create", help="Create a new user")
    c.add_argument("--email", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--role", choices=["admin", "manager", "viewer"], default="viewer")
    c.add_argument(
        "--password", default=None, help="Optional explicit password (otherwise generated)"
    )

    r = sub.add_parser("reset-password", help="Reset password (random or provided)")
    r.add_argument("--email", required=True)
    r.add_argument("--password", default=None)

    s = sub.add_parser("set-role", help="Change a user's role")
    s.add_argument("--email", required=True)
    s.add_argument("--role", choices=["admin", "manager", "viewer"], required=True)

    d = sub.add_parser("deactivate", help="Deactivate a user")
    d.add_argument("--email", required=True)

    a = sub.add_parser("activate", help="Activate a user")
    a.add_argument("--email", required=True)

    return p


COMMANDS = {
    "list": cmd_list,
    "create": cmd_create,
    "reset-password": cmd_reset_password,
    "set-role": cmd_set_role,
    "deactivate": cmd_deactivate,
    "activate": cmd_activate,
}


def main() -> int:
    args = build_parser().parse_args()
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
