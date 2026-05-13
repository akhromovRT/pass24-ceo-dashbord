from fastapi import APIRouter, Depends
from sqlmodel import Session, select, func

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import Organization, OrgStatus, MonthlySnapshot, Alert, AlertStatus

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/summary")
def dashboard_summary(session: Session = Depends(get_session)):
    mrr = session.exec(
        select(func.coalesce(func.sum(Organization.monthly_ap), 0)).where(
            Organization.status == OrgStatus.ACTIVE,
            Organization.monthly_ap.is_not(None),  # type: ignore[union-attr]
        )
    ).one()

    total_debt = session.exec(
        select(func.coalesce(func.sum(Organization.total_debt), 0))
    ).one()

    active_clients = session.exec(
        select(func.count()).select_from(Organization).where(
            Organization.status == OrgStatus.ACTIVE
        )
    ).one()

    open_alerts = session.exec(
        select(func.count()).select_from(Alert).where(
            Alert.status == AlertStatus.OPEN
        )
    ).one()

    return {
        "mrr": float(mrr),
        "arr": float(mrr) * 12,
        "total_debt": float(total_debt),
        "active_clients": active_clients,
        "open_alerts": open_alerts,
    }


@router.get("/mrr-trend")
def mrr_trend(session: Session = Depends(get_session)):
    results = session.exec(
        select(
            MonthlySnapshot.year,
            MonthlySnapshot.month,
            func.sum(MonthlySnapshot.sold_ap).label("sold_ap"),
            func.sum(MonthlySnapshot.paid_ap).label("paid_ap"),
        )
        .group_by(MonthlySnapshot.year, MonthlySnapshot.month)
        .order_by(MonthlySnapshot.year, MonthlySnapshot.month)
    ).all()

    return [
        {
            "year": r[0],
            "month": r[1],
            "sold_ap": float(r[2] or 0),
            "paid_ap": float(r[3] or 0),
        }
        for r in results
    ]


@router.get("/aging")
def aging_buckets(session: Session = Depends(get_session)):
    orgs = session.exec(
        select(Organization).where(
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()

    buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    bucket_counts = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}

    for org in orgs:
        debt = float(org.total_debt or 0)
        monthly = float(org.monthly_ap or 1)
        months_overdue = debt / monthly if monthly > 0 else 0

        if months_overdue <= 1:
            key = "0-30"
        elif months_overdue <= 2:
            key = "31-60"
        elif months_overdue <= 3:
            key = "61-90"
        else:
            key = "90+"

        buckets[key] += debt
        bucket_counts[key] += 1

    return [
        {"bucket": k, "amount": buckets[k], "count": bucket_counts[k]}
        for k in buckets
    ]
