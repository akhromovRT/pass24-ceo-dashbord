"""Построение ленты месячных начислений (monthly_charge) клиента."""

from datetime import date
from decimal import Decimal

from sqlmodel import Session, select

from app.models import (
    ChargeSource,
    Contract,
    ContractType,
    DocType,
    Document,
    MonthlyCharge,
    Organization,
    OrgStatus,
    PaymentAllocation,
    TariffPeriod,
)


def _iter_months(start: date, through: date):
    y, m = start.year, start.month
    while (y, m) <= (through.year, through.month):
        yield y, m
        m += 1
        if m == 13:
            m, y = 1, y + 1


class ChargeService:
    def __init__(self, session: Session):
        self.session = session

    def _charges(self, org_id) -> list[MonthlyCharge]:
        return list(
            self.session.exec(
                select(MonthlyCharge).where(MonthlyCharge.organization_id == org_id)
            ).all()
        )

    def _tariff_for(self, org_id, year: int, month: int) -> Decimal:
        """Тариф, действовавший в (year, month): последний tariff_period
        с valid_from <= первое число месяца."""
        target = date(year, month, 1)
        rows = self.session.exec(
            select(TariffPeriod)
            .where(TariffPeriod.organization_id == org_id, TariffPeriod.valid_from <= target)
            .order_by(TariffPeriod.valid_from.desc())
        ).all()
        return rows[0].monthly_amount if rows else Decimal("0")

    def _realizations(self, org_id) -> dict[tuple[int, int], Document]:
        """SALE-документы subscription-контрактов, ключ (year, month) по doc_date.
        При нескольких за месяц берётся документ с максимальной суммой."""
        rows = self.session.exec(
            select(Document)
            .join(Contract, Contract.id == Document.contract_id)
            .where(
                Document.organization_id == org_id,
                Document.doc_type == DocType.SALE,
                Document.doc_date.is_not(None),
                Contract.contract_type == ContractType.SUBSCRIPTION,
            )
        ).all()
        out: dict[tuple[int, int], Document] = {}
        for d in rows:
            key = (d.doc_date.year, d.doc_date.month)
            if key not in out or (d.amount or 0) > (out[key].amount or 0):
                out[key] = d
        return out

    def charge_start(self, org_id) -> date | None:
        """Месяц первой активности клиента: ранний из valid_from первого
        тарифа, даты первого subscription-SALE, первого платежа."""
        candidates: list[date] = []
        tp = self.session.exec(
            select(TariffPeriod.valid_from)
            .where(TariffPeriod.organization_id == org_id)
            .order_by(TariffPeriod.valid_from)
        ).first()
        if tp:
            candidates.append(tp)
        reals = self._realizations(org_id)
        if reals:
            y, m = min(reals)
            candidates.append(date(y, m, 1))
        first_pay = self.session.exec(
            select(Document.doc_date)
            .where(
                Document.organization_id == org_id,
                Document.doc_type == DocType.PAYMENT,
                Document.doc_date.is_not(None),
            )
            .order_by(Document.doc_date)
        ).first()
        if first_pay:
            candidates.append(date(first_pay.year, first_pay.month, 1))
        return min(candidates) if candidates else None

    def _clear_charges_and_allocs(self, org_id) -> None:
        """Удаляет все monthly_charges клиента вместе с зависимыми
        payment_allocations. Без предварительной чистки allocs DELETE на
        charges падает по FK payment_allocations.monthly_charge_id."""
        charges = list(self._charges(org_id))
        if not charges:
            return
        charge_ids = [c.id for c in charges]
        for a in self.session.exec(
            select(PaymentAllocation).where(
                PaymentAllocation.monthly_charge_id.in_(charge_ids)  # type: ignore[union-attr]
            )
        ).all():
            self.session.delete(a)
        self.session.flush()
        for c in charges:
            self.session.delete(c)
        self.session.flush()

    def rebuild_for_organization(self, org_id, start: date, through: date) -> None:
        """Пересобирает monthly_charge клиента за [start, through].
        Удаляет старые начисления клиента и строит заново. Приоритет —
        реальная 1С-Реализация, синтетика из тарифа — для пропусков.

        Для клиента в статусе CHURNED или TRANSIT с заполненным churn_month
        верхняя граница period подрезается до churn_month — после месяца
        отключения начисления не создаются и долг не накапливается.
        TRANSIT — это юр.лицо, переставшее платить (переоформление ИНН,
        транзитный плательщик за другого клиента)."""
        org = self.session.get(Organization, org_id)
        if (
            org is not None
            and org.status in (OrgStatus.CHURNED, OrgStatus.TRANSIT)
            and org.churn_month is not None
        ):
            if org.churn_month < start:
                # Месяц отключения раньше точки начала ленты — лента пуста.
                self._clear_charges_and_allocs(org_id)
                return
            if org.churn_month < through:
                through = org.churn_month
        self._clear_charges_and_allocs(org_id)
        realizations = self._realizations(org_id)
        for year, month in _iter_months(start, through):
            real = realizations.get((year, month))
            if real is not None and (real.amount or 0) > 0:
                self.session.add(
                    MonthlyCharge(
                        organization_id=org_id,
                        year=year,
                        month=month,
                        amount=real.amount,
                        source=ChargeSource.REALIZATION_1C,
                        source_document_id=real.id,
                    )
                )
            else:
                self.session.add(
                    MonthlyCharge(
                        organization_id=org_id,
                        year=year,
                        month=month,
                        amount=self._tariff_for(org_id, year, month),
                        source=ChargeSource.SYNTHETIC_TARIFF,
                    )
                )
        self.session.flush()
