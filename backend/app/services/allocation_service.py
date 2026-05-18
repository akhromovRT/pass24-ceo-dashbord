"""Разнесение платежей по месячным начислениям (детерминированный пересчёт)."""
from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.models import (
    AllocationBasis,
    ChargeSource,
    Contract,
    Document,
    DocType,
    MonthlyCharge,
    PaymentAllocation,
)
from app.parser.period_extraction import extract_periods

_ADVANCE_HORIZON_MONTHS = 24
_PAYMENTS_CONTRACT = "1C-PAYMENTS"


class AllocationService:
    def __init__(self, session: Session):
        self.session = session

    def _charges(self, org_id) -> list[MonthlyCharge]:
        return list(self.session.exec(
            select(MonthlyCharge)
            .where(MonthlyCharge.organization_id == org_id)
            .order_by(MonthlyCharge.year, MonthlyCharge.month)
        ).all())

    def _payments(self, org_id) -> list[Document]:
        """Платежи клиента из реестра «Оплата от покупателей» (синтетический
        контракт 1C-PAYMENTS), amount > 0, в хронологическом порядке.
        payment_kind == other исключаются ниже."""
        rows = self.session.exec(
            select(Document)
            .join(Contract, Contract.id == Document.contract_id)
            .where(Document.organization_id == org_id,
                   Document.doc_type == DocType.PAYMENT,
                   Document.amount > 0,
                   Contract.contract_number == _PAYMENTS_CONTRACT)
        ).all()
        result = []
        for d in rows:
            ep = extract_periods(d.raw_name or "", d.doc_date or date.today())
            if ep.payment_kind != "other":
                result.append(d)
        return sorted(result, key=lambda d: (d.doc_date or date.min,
                                             d.doc_number or "", str(d.id)))

    def _manual_for_payment(self, payment_id) -> Decimal:
        rows = self.session.exec(
            select(PaymentAllocation).where(
                PaymentAllocation.payment_document_id == payment_id,
                PaymentAllocation.is_manual == True)  # noqa: E712
        ).all()
        return sum((a.allocated_amount for a in rows), Decimal("0"))

    def recompute_for_organization(self, org_id) -> None:
        """Удаляет авто-аллокации клиента и переразносит все subscription-платежи.
        Ручные аллокации (is_manual=True) сохраняются."""
        charges = self._charges(org_id)
        payments = self._payments(org_id)
        org_payment_ids = {d.id for d in payments}

        # удалить авто-аллокации (manual сохраняются)
        for a in self.session.exec(select(PaymentAllocation)).all():
            if a.payment_document_id in org_payment_ids and not a.is_manual:
                self.session.delete(a)
        self.session.flush()

        # остаток по каждому начислению с учётом сохранённых ручных аллокаций
        outstanding: dict = {}
        for c in charges:
            manual = self.session.exec(
                select(PaymentAllocation)
                .where(PaymentAllocation.monthly_charge_id == c.id,
                       PaymentAllocation.is_manual == True)  # noqa: E712
            ).all()
            used = sum((a.allocated_amount for a in manual), Decimal("0"))
            outstanding[c.id] = (c, c.amount - used)

        for payment in payments:
            remaining = (payment.amount or Decimal("0")) - self._manual_for_payment(payment.id)
            if remaining <= 0:
                continue

            ep = extract_periods(payment.raw_name or "",
                                 payment.doc_date or date.today())

            # 1. явные периоды из назначения
            charge_by_period = {(c.year, c.month): c for c in charges}
            for (py, pm) in ep.periods:
                if remaining <= 0:
                    break
                c = charge_by_period.get((py, pm))
                if c is None:
                    continue
                _, left = outstanding[c.id]
                if left <= 0:
                    continue
                take = min(remaining, left)
                self.session.add(PaymentAllocation(
                    payment_document_id=payment.id, monthly_charge_id=c.id,
                    allocated_amount=take, basis=AllocationBasis.EXPLICIT_PERIOD,
                ))
                outstanding[c.id] = (c, left - take)
                remaining -= take

            # 2. FIFO — гашение от самого старого начисления
            remaining = self._fifo(payment, remaining, outstanding, charges)

            # 3. аванс в будущие начисления
            if remaining > 0:
                remaining = self._spill_advance(org_id, payment, remaining,
                                                outstanding, charges)

            # 4. нераспознанный остаток
            if remaining > 0:
                self.session.add(PaymentAllocation(
                    payment_document_id=payment.id, monthly_charge_id=None,
                    allocated_amount=remaining, basis=AllocationBasis.ADVANCE,
                ))
        self.session.flush()

    def _fifo(self, payment, remaining: Decimal, outstanding: dict,
              charges: list[MonthlyCharge]) -> Decimal:
        for c in charges:
            if remaining <= 0:
                break
            _, left = outstanding[c.id]
            if left <= 0:
                continue
            take = min(remaining, left)
            self.session.add(PaymentAllocation(
                payment_document_id=payment.id, monthly_charge_id=c.id,
                allocated_amount=take, basis=AllocationBasis.FIFO,
            ))
            outstanding[c.id] = (c, left - take)
            remaining -= take
        return remaining

    def _spill_advance(self, org_id, payment, remaining: Decimal,
                       outstanding: dict, charges: list[MonthlyCharge]) -> Decimal:
        """Остаток уходит авансом в синтетические будущие начисления."""
        from app.services.charge_service import ChargeService
        last = max(((c.year, c.month) for c in charges), default=None)
        if last is None:
            return remaining
        y, m = last
        created = 0
        while remaining > 0 and created < _ADVANCE_HORIZON_MONTHS:
            m += 1
            if m == 13:
                m, y = 1, y + 1
            created += 1
            tariff = ChargeService(self.session)._tariff_for(org_id, y, m)
            if tariff <= 0:
                break
            charge = MonthlyCharge(organization_id=org_id, year=y, month=m,
                                   amount=tariff, source=ChargeSource.SYNTHETIC_TARIFF)
            self.session.add(charge)
            self.session.flush()
            charges.append(charge)
            take = min(remaining, tariff)
            self.session.add(PaymentAllocation(
                payment_document_id=payment.id, monthly_charge_id=charge.id,
                allocated_amount=take, basis=AllocationBasis.ADVANCE,
            ))
            outstanding[charge.id] = (charge, tariff - take)
            remaining -= take
        return remaining
