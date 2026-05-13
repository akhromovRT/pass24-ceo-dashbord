from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import Organization

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
            Organization.total_debt.is_not(None),  # type: ignore[union-attr]
            Organization.total_debt > min_debt,  # type: ignore[operator]
        )
        .order_by(Organization.total_debt.desc())  # type: ignore[union-attr]
    )
    debtors = session.exec(query).all()
    return debtors
