from datetime import date
from decimal import Decimal

from sqlmodel import select

from app.models import (
    Contract,
    ContractType,
    Document,
    DocType,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    TariffPeriod,
)
from app.services.build_ledger import build_ledger


def test_build_ledger_end_to_end(db_session):
    org = Organization(inn="7700000020", name_1c="Полный Клиент",
                       status=OrgStatus.ACTIVE, monthly_ap=Decimal("9000"))
    db_session.add(org)
    db_session.flush()
    contract = Contract(organization_id=org.id, contract_type=ContractType.OTHER,
                        contract_number="BANK-IMPORT", raw_name="bank")
    db_session.add(contract)
    db_session.flush()
    db_session.add(Document(contract_id=contract.id, organization_id=org.id,
                            doc_type=DocType.PAYMENT, doc_date=date(2026, 2, 10),
                            amount=Decimal("9000"), raw_name="оплата за доступ"))
    db_session.commit()

    summary = build_ledger(db_session)

    assert db_session.exec(select(TariffPeriod)).first() is not None
    assert db_session.exec(select(MonthlyCharge)).first() is not None
    assert db_session.exec(select(PaymentAllocation)).first() is not None
    assert summary["tariffs_seeded"] >= 1
    assert summary["orgs_rebuilt"] >= 1
