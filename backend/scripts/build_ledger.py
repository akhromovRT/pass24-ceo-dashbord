"""CLI: backfill AR-леджера по существующим данным.

Запуск: cd backend && python -m scripts.build_ledger
"""

from sqlmodel import Session, create_engine

from app.core.config import settings
from app.services.build_ledger import build_ledger


def main() -> None:
    engine = create_engine(str(settings.DATABASE_URL), echo=False)
    with Session(engine) as session:
        summary = build_ledger(session)
    print(f"Backfill завершён: {summary}")


if __name__ == "__main__":
    main()
