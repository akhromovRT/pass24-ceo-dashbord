"""Ручная правка разнесения платежа по начислениям леджера."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import AllocationBasis, Document, MonthlyCharge, PaymentAllocation
from app.services.allocation_service import AllocationService

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(get_current_user)],
)


class AllocationItem(BaseModel):
    year: int
    month: int
    amount: float


class AllocationOverride(BaseModel):
    allocations: list[AllocationItem]


@router.put("/{document_id}/allocations")
def override_allocations(
    document_id: uuid.UUID,
    payload: AllocationOverride,
    session: Session = Depends(get_session),
):
    """Заменяет разнесение платежа списком ручных аллокаций. Строки
    помечаются is_manual=True и не перезатираются автоматическим пересчётом."""
    payment = session.get(Document, document_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found")

    for a in session.exec(
        select(PaymentAllocation).where(
            PaymentAllocation.payment_document_id == document_id
        )
    ).all():
        session.delete(a)
    session.flush()

    for item in payload.allocations:
        charge = session.exec(
            select(MonthlyCharge).where(
                MonthlyCharge.organization_id == payment.organization_id,
                MonthlyCharge.year == item.year,
                MonthlyCharge.month == item.month,
            )
        ).first()
        session.add(PaymentAllocation(
            payment_document_id=document_id,
            monthly_charge_id=charge.id if charge else None,
            allocated_amount=Decimal(str(item.amount)),
            basis=AllocationBasis.MANUAL,
            is_manual=True,
        ))
    session.flush()

    AllocationService(session).recompute_for_organization(payment.organization_id)
    session.commit()
    return {"status": "ok"}
