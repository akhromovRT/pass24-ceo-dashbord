"""CLI: импорт реестра «Оплата от покупателей» из 1С.

Запуск: cd backend && python -m scripts.import_payments <path-to-xls>

Создаёт PAYMENT-документы на синтетическом контракте 1C-PAYMENTS —
источник платежей для AR-леджера. После импорта запустить build_ledger.
"""
import hashlib
import sys

from sqlmodel import Session, create_engine

from app.core.config import settings
from app.parser.payments_report import parse_payments_report
from app.services.import_service import ImportService


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.import_payments <path-to-file>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()

    print(f"Парсинг {path} ...")
    result = parse_payments_report(path)
    print(f"Распарсено платежей: {len(result.payments)}")

    engine = create_engine(str(settings.DATABASE_URL), echo=False)
    with Session(engine) as session:
        run = ImportService(session).process_payments_report(result, file_hash=file_hash)
    print(f"Импорт завершён: {run.documents_count} документов, "
          f"{run.buyers_count} клиентов, новых {run.new_buyers}")


if __name__ == "__main__":
    main()
