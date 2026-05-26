import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic import Field as PydField
from sqlmodel import Session, col, func, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    ClientObject,
    Contract,
    DocType,
    Document,
    MonthlyCharge,
    MonthlySnapshot,
    Organization,
    OrgStatus,
    OrgType,
    PaymentAllocation,
    TariffPeriod,
)

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)


_SORTABLE_COLUMNS = {
    "name_display": Organization.name_display,
    "name_1c": Organization.name_1c,
    "inn": Organization.inn,
    "monthly_ap": Organization.monthly_ap,
    "total_debt": Organization.total_debt,
    "payment_score": Organization.payment_score,
    "status": Organization.status,
    "churn_month": Organization.churn_month,
    "objects": Organization.objects,
    "city_region": Organization.city_region,
}


@router.get("")
def list_organizations(
    search: str | None = None,
    status: OrgStatus | None = None,
    manager_id: uuid.UUID | None = None,
    sort_by: str | None = None,
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    query = select(Organization)
    count_query = select(func.count()).select_from(Organization)

    if search:
        pattern = f"%{search}%"
        filter_cond = col(Organization.name_display).ilike(pattern) | col(
            Organization.name_1c
        ).ilike(pattern) | col(Organization.inn).ilike(pattern)
        query = query.where(filter_cond)
        count_query = count_query.where(filter_cond)

    if status:
        query = query.where(Organization.status == status)
        count_query = count_query.where(Organization.status == status)

    if manager_id:
        query = query.where(Organization.manager_id == manager_id)
        count_query = count_query.where(Organization.manager_id == manager_id)

    if sort_by and sort_by in _SORTABLE_COLUMNS:
        column = _SORTABLE_COLUMNS[sort_by]
        order_clause = col(column).desc() if sort_dir == "desc" else col(column).asc()
        query = query.order_by(order_clause.nulls_last())
    else:
        query = query.order_by(col(Organization.name_display).asc().nulls_last())

    total = session.exec(count_query).one()
    offset = (page - 1) * page_size
    items = session.exec(query.offset(offset).limit(page_size)).all()

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{inn}")
def get_organization(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/{inn}/snapshots")
def get_organization_snapshots(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    snapshots = session.exec(
        select(MonthlySnapshot)
        .where(MonthlySnapshot.organization_id == org.id)
        .order_by(MonthlySnapshot.year, MonthlySnapshot.month)
    ).all()
    return snapshots


@router.get("/{inn}/contracts")
def get_organization_contracts(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    contracts = session.exec(
        select(Contract).where(Contract.organization_id == org.id)
    ).all()
    return contracts


@router.get("/{inn}/objects")
def get_organization_objects(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    objects = session.exec(
        select(ClientObject)
        .where(ClientObject.organization_id == org.id)
        .order_by(ClientObject.name)
    ).all()
    return objects


@router.get("/{inn}/documents")
def get_organization_documents(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    docs = session.exec(
        select(Document)
        .where(Document.organization_id == org.id)
        .order_by(col(Document.doc_date).desc())
    ).all()
    return docs


class OrganizationUpdate(BaseModel):
    """Частичное обновление. Read-only поля (inn, name_1c, total_debt,
    payment_score, *_raw) сюда не входят — источник истины импорт из 1С."""
    model_config = ConfigDict(extra="ignore")

    name_display: str | None = None
    org_type: OrgType | None = None
    status: OrgStatus | None = None
    churn_month: date | None = None
    manager_id: uuid.UUID | None = None
    client_since: date | None = None
    objects: int | None = None
    object_type: str | None = None
    cloud_url: str | None = None
    system_number: str | None = None
    equipment: str | None = None
    address: str | None = None
    city_region: str | None = None
    has_folder: bool | None = None
    monthly_ap: Decimal | None = PydField(default=None, ge=0)
    notes: str | None = None
    doc_exchange: str | None = None
    in_registry: bool | None = None
    excluded_from_analytics: bool | None = None
    excluded_reason: str | None = None

    @field_validator("churn_month")
    @classmethod
    def _normalize_churn_month(cls, v: date | None) -> date | None:
        """Гранулярность — месяц. День приводится к 1-му."""
        if v is None:
            return None
        return date(v.year, v.month, 1)


def _last_payment_month(session: Session, org_id: uuid.UUID) -> date | None:
    """Месяц (1-е число) последнего платежа клиента, либо None."""
    q = select(func.max(Document.doc_date)).where(
        Document.organization_id == org_id,
        Document.doc_type == DocType.PAYMENT,
        Document.doc_date.is_not(None),  # type: ignore[union-attr]
    )
    last_dt = session.exec(q).one()
    if last_dt is None:
        return None
    return date(last_dt.year, last_dt.month, 1)


@router.patch("/{inn}")
def update_organization(
    inn: str,
    payload: OrganizationUpdate,
    session: Session = Depends(get_session),
):
    q = select(Organization).where(Organization.inn == inn)
    org = session.exec(q).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    prev_status = org.status
    prev_churn_month = org.churn_month
    changes = payload.model_dump(exclude_unset=True)

    # Логика churn_month вокруг смены статуса. CHURNED — клиент ушёл;
    # TRANSIT — юр.лицо больше не платит за себя (переоформление ИНН либо
    # был транзитным плательщиком за другого клиента). В обоих случаях
    # начисления прекращаются с churn_month.
    new_status = changes.get("status", prev_status)
    churn_in_payload = "churn_month" in changes

    if new_status in (OrgStatus.CHURNED, OrgStatus.TRANSIT):
        if not churn_in_payload and prev_churn_month is None:
            auto = _last_payment_month(session, org.id)
            if auto is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "У клиента нет ни одного платежа — установите месяц "
                        "отключения вручную (поле churn_month)."
                    ),
                )
            changes["churn_month"] = auto
    else:
        if not churn_in_payload:
            changes["churn_month"] = None

    for key, value in changes.items():
        setattr(org, key, value)
    org.updated_at = datetime.now(UTC)
    session.add(org)
    session.flush()

    # Пересборка леджера только для этого клиента
    status_changed = prev_status != org.status
    churn_changed = prev_churn_month != org.churn_month
    if status_changed or churn_changed:
        from app.services.allocation_service import AllocationService
        from app.services.charge_service import ChargeService
        charge_svc = ChargeService(session)
        start = charge_svc.charge_start(org.id)
        if start is not None:
            charge_svc.rebuild_for_organization(
                org.id, start=start, through=date.today(),
            )
            AllocationService(session).recompute_for_organization(org.id)

    session.commit()
    session.refresh(org)
    return org


@router.get("/{inn}/ledger")
def organization_ledger(inn: str, session: Session = Depends(get_session)):
    """Леджер клиента: лента месячных начислений + платежи с разнесением."""
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    charges = session.exec(
        select(MonthlyCharge)
        .where(MonthlyCharge.organization_id == org.id)
        .order_by(MonthlyCharge.year, MonthlyCharge.month)
    ).all()
    alloc_by_charge: dict = {}
    for a in session.exec(
        select(PaymentAllocation)
        .join(MonthlyCharge, MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
        .where(MonthlyCharge.organization_id == org.id)
    ).all():
        alloc_by_charge[a.monthly_charge_id] = (
            alloc_by_charge.get(a.monthly_charge_id, Decimal("0")) + a.allocated_amount
        )

    months = []
    for c in charges:
        allocated = alloc_by_charge.get(c.id, Decimal("0"))
        outstanding = (c.amount or Decimal("0")) - allocated
        if allocated <= 0:
            status = "unpaid"
        elif outstanding > 0:
            status = "partial"
        else:
            status = "paid"
        months.append({
            "year": c.year, "month": c.month, "accrued": float(c.amount or 0),
            "allocated": float(allocated), "outstanding": float(outstanding),
            "status": status, "source": c.source.value,
        })

    payments = []
    for d in session.exec(
        select(Document)
        .where(Document.organization_id == org.id,
               Document.doc_type == DocType.PAYMENT,
               Document.amount > 0)
        .order_by(col(Document.doc_date))
    ).all():
        allocs = session.exec(
            select(PaymentAllocation, MonthlyCharge)
            .join(MonthlyCharge,
                  MonthlyCharge.id == PaymentAllocation.monthly_charge_id,
                  isouter=True)
            .where(PaymentAllocation.payment_document_id == d.id)
        ).all()
        payments.append({
            "id": str(d.id),
            "doc_date": str(d.doc_date) if d.doc_date else None,
            "amount": float(d.amount or 0),
            "raw_name": d.raw_name,
            "allocations": [
                {"year": mc.year if mc else None,
                 "month": mc.month if mc else None,
                 "amount": float(a.allocated_amount), "basis": a.basis.value,
                 "is_manual": a.is_manual}
                for a, mc in allocs
            ],
        })
    return {"months": months, "payments": payments}


class TariffPeriodCreate(BaseModel):
    valid_from: date
    monthly_amount: Decimal = PydField(ge=0)


@router.get("/{inn}/tariffs")
def organization_tariffs(inn: str, session: Session = Depends(get_session)):
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    rows = session.exec(
        select(TariffPeriod)
        .where(TariffPeriod.organization_id == org.id)
        .order_by(col(TariffPeriod.valid_from).desc())
    ).all()
    return [{"id": str(t.id), "valid_from": str(t.valid_from),
             "monthly_amount": float(t.monthly_amount)} for t in rows]


@router.post("/{inn}/tariffs")
def add_organization_tariff(
    inn: str,
    payload: TariffPeriodCreate,
    session: Session = Depends(get_session),
    user=Depends(get_current_user),
):
    """Добавляет тариф, пересобирает начисления и пересчитывает леджер клиента."""
    org = session.exec(
        select(Organization).where(Organization.inn == inn)
    ).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    tp = TariffPeriod(organization_id=org.id, valid_from=payload.valid_from,
                      monthly_amount=payload.monthly_amount, created_by=user.id)
    session.add(tp)
    org.monthly_ap = payload.monthly_amount
    org.updated_at = datetime.now(UTC)
    session.add(org)
    session.flush()

    from app.services.allocation_service import AllocationService
    from app.services.charge_service import ChargeService
    charge_svc = ChargeService(session)
    start = charge_svc.charge_start(org.id) or payload.valid_from
    charge_svc.rebuild_for_organization(org.id, start=start, through=date.today())
    AllocationService(session).recompute_for_organization(org.id)
    session.commit()
    return {"status": "ok", "id": str(tp.id)}
