from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, col, func, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models.contract import Contract
from app.models.organization import Organization

router = APIRouter(
    prefix="/contracts",
    tags=["contracts"],
    dependencies=[Depends(get_current_user)],
)

SORT_FIELDS = {
    "monthly_amount": col(Contract.monthly_amount),
    "contract_date": col(Contract.contract_date),
    "org_name": col(Organization.name_1c),
}


@router.get("")
def list_contracts(
    search: str | None = None,
    sort_by: str = Query(default="org_name", pattern="^(monthly_amount|contract_date|org_name)$"),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
):
    base = select(Contract, Organization).join(
        Organization, Contract.organization_id == Organization.id
    )
    count_base = (
        select(func.count())
        .select_from(Contract)
        .join(Organization, Contract.organization_id == Organization.id)
    )

    if search:
        pattern = f"%{search}%"
        cond = (
            col(Organization.name_1c).ilike(pattern)
            | col(Organization.name_display).ilike(pattern)
            | col(Organization.inn).ilike(pattern)
            | col(Contract.contract_number).ilike(pattern)
            | col(Contract.raw_name).ilike(pattern)
        )
        base = base.where(cond)
        count_base = count_base.where(cond)

    sort_col = SORT_FIELDS.get(sort_by, col(Organization.name_1c))
    base = base.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    total = session.exec(count_base).one()
    offset = (page - 1) * page_size
    rows = session.exec(base.offset(offset).limit(page_size)).all()

    items = [
        {
            "id": str(c.id),
            "contract_number": c.contract_number,
            "contract_date": c.contract_date.isoformat() if c.contract_date else None,
            "contract_type": c.contract_type,
            "monthly_amount": float(c.monthly_amount) if c.monthly_amount else None,
            "status": c.status,
            "raw_name": c.raw_name,
            "org_inn": o.inn,
            "org_name": o.name_display or o.name_1c,
            "org_object_type": o.object_type,
            "org_cloud_url": o.cloud_url,
            "org_system_number": o.system_number,
            "org_equipment": o.equipment,
            "org_address": o.address,
            "org_city": o.city_region,
        }
        for c, o in rows
    ]

    return {"items": items, "total": total, "page": page, "page_size": page_size}
