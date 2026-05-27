"""GET /api/v1/registry — плоский список «компания × объект» для UI «Реестр клиентов».

Возвращает все организации с in_registry=True. Для компаний с N объектами
возвращается N строк; для компаний без объектов в client_objects — одна
строка с пустыми object-полями. Клиент-сайд DataTable сам сортирует и
фильтрует — поэтому без пагинации (~200-500 строк норм).
"""
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from app.api.v1.auth import get_current_user
from app.core.database import get_session
from app.models import ClientObject, Organization

router = APIRouter(
    prefix="/registry",
    tags=["registry"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_registry(
    only_in_registry: bool = Query(default=True),
    session: Session = Depends(get_session),
):
    if only_in_registry:
        orgs = session.exec(
            select(Organization).where(Organization.in_registry == True)  # noqa: E712
        ).all()
    else:
        orgs = session.exec(select(Organization)).all()

    objs = session.exec(select(ClientObject)).all()
    by_org: dict = {}
    for o in objs:
        by_org.setdefault(o.organization_id, []).append(o)

    items = []
    objects_total = 0
    for org in orgs:
        org_objects = by_org.get(org.id, [])
        # «Количество объектов» (Софья, 2026-05-26): фактические client_objects,
        # иначе objects_count_declared из реестра, fallback — 1 (одна Organization
        # в реестре = минимум один объект, иначе её бы здесь не было).
        objects_total += len(org_objects) if org_objects else (org.objects_count_declared or 1)
        if org_objects:
            for co in org_objects:
                items.append({
                    "id": f"{org.id}:{co.id}",
                    "org_id": str(org.id),
                    "object_id": str(co.id),
                    "company": org.name_display or org.name_1c,
                    "inn": org.inn,
                    "object_name": co.name,
                    "contract_1c": org.contract_1c_raw,
                    "active_doc": org.active_doc_raw,
                    "cloud_url": co.cloud_url,
                    "object_number": co.object_number,
                    "objects_count": org.objects_count_declared,
                    "object_type": co.object_type,
                    "address": co.address,
                    "city_region": co.city_region,
                    "doc_exchange": org.doc_exchange,
                    "in_registry": org.in_registry,
                    "status": org.status,
                    "monthly_ap": float(org.monthly_ap) if org.monthly_ap is not None else None,
                    "total_debt": float(org.total_debt) if org.total_debt is not None else None,
                })
        else:
            items.append({
                "id": f"{org.id}:_no_object",
                "org_id": str(org.id),
                "object_id": None,
                "company": org.name_display or org.name_1c,
                "inn": org.inn,
                "object_name": None,
                "contract_1c": org.contract_1c_raw,
                "active_doc": org.active_doc_raw,
                "cloud_url": org.cloud_url,
                "object_number": org.system_number,
                "objects_count": org.objects_count_declared,
                "object_type": org.object_type,
                "address": org.address,
                "city_region": org.city_region,
                "doc_exchange": org.doc_exchange,
                "in_registry": org.in_registry,
                "status": org.status,
                "monthly_ap": float(org.monthly_ap) if org.monthly_ap is not None else None,
                "total_debt": float(org.total_debt) if org.total_debt is not None else None,
            })

    return {
        "items": items,
        "total": len(items),
        "companies": len(orgs),
        "objects": objects_total,
    }
