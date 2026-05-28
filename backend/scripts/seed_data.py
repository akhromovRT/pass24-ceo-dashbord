"""Seed script: creates admin user and imports analytics spreadsheet data.

Usage:
    cd backend && python -m scripts.seed_data [path_to_analytics.xlsx]
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.contract import Contract, ContractStatus
from app.models.organization import Organization, OrgStatus
from app.models.snapshot import MonthlySnapshot
from app.models.user import User, UserRole
from app.parser.analytics_migration import parse_analytics
from app.parser.classifier import classify_contract

DEFAULT_ANALYTICS_PATH = (
    Path.home()
    / "Library/Mobile Documents/com~apple~CloudDocs/ClaudeCode"
    / "Аналитика поступлений/Аналитика_поступлений_2025_2026.xlsx"
)

STATUS_MAP = {
    "Активен": OrgStatus.ACTIVE,
    "Расторгнут": OrgStatus.CHURNED,
    "Приостановлен": OrgStatus.SUSPENDED,
    "Уточнить": OrgStatus.ACTIVE,
    "Новый": OrgStatus.ACTIVE,
}


def create_admin(session: Session) -> User:
    existing = session.exec(select(User).where(User.email == "admin@onvi-service.ru")).first()
    if existing:
        print(f"Admin already exists: {existing.email}")
        return existing

    admin = User(
        name="Администратор",
        email="admin@onvi-service.ru",
        hashed_password=get_password_hash("admin"),
        role=UserRole.ADMIN,
    )
    session.add(admin)
    session.flush()
    print(f"Created admin: {admin.email}")
    return admin


def import_analytics(session: Session, file_path: Path) -> None:
    if not file_path.exists():
        print(f"Analytics file not found: {file_path}")
        return

    rows = parse_analytics(file_path)
    print(f"Parsed {len(rows)} rows from analytics spreadsheet")

    orgs_created = 0
    orgs_updated = 0
    contracts_created = 0
    snapshots_created = 0

    for row in rows:
        org = session.exec(select(Organization).where(Organization.inn == row.inn)).first()

        if org is None:
            org = Organization(
                inn=row.inn,
                name_1c=row.name,
                name_display=row.name,
                monthly_ap=row.monthly_ap,
                object_type=row.object_type,
                cloud_url=row.cloud_url,
                system_number=row.system_number,
                equipment=row.equipment,
                address=row.address,
                city_region=row.city_region,
                status=STATUS_MAP.get(row.status or "", OrgStatus.ACTIVE),
            )
            session.add(org)
            session.flush()
            orgs_created += 1
        else:
            if row.monthly_ap and not org.monthly_ap:
                org.monthly_ap = row.monthly_ap
            if row.object_type and not org.object_type:
                org.object_type = row.object_type
            if row.cloud_url and not org.cloud_url:
                org.cloud_url = row.cloud_url
            if row.system_number and not org.system_number:
                org.system_number = row.system_number
            if row.equipment and not org.equipment:
                org.equipment = row.equipment
            if row.address and not org.address:
                org.address = row.address
            if row.city_region and not org.city_region:
                org.city_region = row.city_region
            session.add(org)
            session.flush()
            orgs_updated += 1

        if row.contract_raw:
            existing_contract = session.exec(
                select(Contract).where(
                    Contract.organization_id == org.id,
                    Contract.raw_name == row.contract_raw,
                )
            ).first()

            if not existing_contract:
                classification = classify_contract(row.contract_raw)
                contract = Contract(
                    organization_id=org.id,
                    contract_number=row.contract_raw,
                    contract_date=row.contract_date,
                    contract_type=classification.type,
                    classification_source=classification.source,
                    classification_rule=classification.rule,
                    monthly_amount=row.monthly_ap,
                    raw_name=row.contract_raw,
                    status=ContractStatus.ACTIVE,
                )
                session.add(contract)
                session.flush()
                contracts_created += 1

        for (year, month), (plan, fact) in row.monthly_data.items():
            existing_snap = session.exec(
                select(MonthlySnapshot).where(
                    MonthlySnapshot.organization_id == org.id,
                    MonthlySnapshot.year == year,
                    MonthlySnapshot.month == month,
                    MonthlySnapshot.import_run_id == None,  # noqa: E711
                )
            ).first()

            if existing_snap:
                continue

            snapshot = MonthlySnapshot(
                organization_id=org.id,
                year=year,
                month=month,
                plan_amount=plan,
                paid=fact,
                sold=plan,
                is_active=True,
            )
            session.add(snapshot)
            snapshots_created += 1

        if (orgs_created + orgs_updated) % 50 == 0:
            session.flush()

    session.commit()
    print(f"Organizations: {orgs_created} created, {orgs_updated} updated")
    print(f"Contracts created: {contracts_created}")
    print(f"Monthly snapshots created: {snapshots_created}")


def main() -> None:
    analytics_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ANALYTICS_PATH

    engine = create_engine(str(settings.DATABASE_URL), echo=False)
    with Session(engine) as session:
        create_admin(session)
        import_analytics(session, analytics_path)
        session.commit()

    print("Seed complete.")


if __name__ == "__main__":
    main()
