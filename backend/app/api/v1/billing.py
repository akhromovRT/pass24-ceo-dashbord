from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, func, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import DocType, Document, Organization
from app.services.aging import aging_index

router = APIRouter(
    prefix="/billing",
    tags=["billing"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/debtors")
def list_debtors(
    min_debt: float = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    query = (
        select(Organization)
        .where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > min_debt,  # type: ignore[operator]
        )
        .order_by(Organization.total_debt.desc())  # type: ignore[union-attr]
    )
    debtors = session.exec(query).all()
    aging = aging_index(session)  # возраст долга — по календарным месяцам
    out = []
    for o in debtors:
        debt = float(o.total_debt or 0)
        monthly = float(o.monthly_ap or 0)
        bucket, age = aging.get(o.id, ("90+", None))
        out.append({
            "id": str(o.id), "inn": o.inn,
            "name": o.name_display or o.name_1c,
            "monthly_ap": monthly or None,
            "total_debt": debt,
            "payment_score": o.payment_score,
            "status": o.status,
            "churn_month": o.churn_month.isoformat() if o.churn_month else None,
            "manager_id": str(o.manager_id) if o.manager_id else None,
            "months_overdue": age,
            "aging_bucket": bucket,
        })
    return out


@router.get("/segments")
def segments(session: Session = Depends(get_session)):
    """Сегментация клиентов реестра по собираемости закрытого месяца."""
    today = date.today()
    prev_y, prev_m = ((today.year, today.month - 1) if today.month > 1
                      else (today.year - 1, 12))

    orgs = session.exec(
        select(Organization).where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.in_registry == True,  # noqa: E712
        )
    ).all()
    org_ids = [o.id for o in orgs]

    paid_by_org: dict = {}
    if org_ids:
        rows = session.exec(
            select(Document.organization_id, func.sum(Document.amount))
            .where(
                Document.doc_type == DocType.PAYMENT,
                Document.organization_id.in_(org_ids),  # type: ignore[union-attr]
                func.extract("year", Document.doc_date) == prev_y,
                func.extract("month", Document.doc_date) == prev_m,
            )
            .group_by(Document.organization_id)
        ).all()
        paid_by_org = {oid: float(s or 0) for oid, s in rows}

    total = len(orgs)
    mrr_plan = sum(float(o.monthly_ap or 0) for o in orgs)
    paying = partial = not_paying = debtors = 0
    for o in orgs:
        plan = float(o.monthly_ap or 0)
        paid = paid_by_org.get(o.id, 0.0)
        ratio = (paid / plan * 100) if plan > 0 else 0
        if ratio >= 95:
            paying += 1
        elif ratio >= 1:
            partial += 1
        else:
            not_paying += 1
        if float(o.total_debt or 0) > 0:
            debtors += 1

    return {
        "total": total, "mrr_plan": round(mrr_plan, 2),
        "paying": paying, "partial": partial,
        "not_paying": not_paying, "debtors": debtors,
        "fact_month": f"{prev_y}-{prev_m:02d}",
    }
