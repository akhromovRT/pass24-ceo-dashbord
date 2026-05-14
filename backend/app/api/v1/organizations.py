import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func, col

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import (
    ClientObject,
    Contract,
    MonthlySnapshot,
    Organization,
    OrgStatus,
)

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_organizations(
    search: str | None = None,
    status: OrgStatus | None = None,
    manager_id: uuid.UUID | None = None,
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
