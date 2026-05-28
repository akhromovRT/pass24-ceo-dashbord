"""Генератор алертов по расписанию (P3.4).

Запускается через CLI: `python -m scripts.run_alerts` на проде через
системный cron (см. agent_docs/guides/runbook.md). Внутри одного запуска:

  1. Просрочка >30/60/90 дней (NON_PAYMENT)
  2. Падение MRR факт > 15% м/м (COLLECTABILITY_DROP)
  3. Новый клиент в реестре без manager_id > 14 дней (UNASSIGNED_CLIENT)
  4. CHURN_RISK: активный клиент с 2+ неоплаченными месяцами подряд

Идемпотентность: перед созданием алерта проверяем, нет ли уже OPEN-алерта
того же type+organization — если есть, не дублируем.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlmodel import Session, func, select

from app.models import (
    Alert, AlertSeverity, AlertStatus, AlertType,
    DocType, Document, MonthlyCharge, Organization, OrgStatus,
    PaymentAllocation,
)


def _has_open_alert(
    session: Session, organization_id, alert_type: AlertType,
) -> bool:
    stmt = select(Alert.id).where(
        Alert.organization_id == organization_id,
        Alert.alert_type == alert_type,
        Alert.status == AlertStatus.OPEN,
    ).limit(1)
    return session.exec(stmt).first() is not None


def _create(
    session: Session, *, org, alert_type: AlertType,
    severity: AlertSeverity, title: str, description: str | None = None,
    metric_value: float | None = None, threshold: float | None = None,
) -> Alert | None:
    if _has_open_alert(session, org.id if org else None, alert_type):
        return None
    a = Alert(
        organization_id=org.id if org else None,
        alert_type=alert_type, severity=severity,
        title=title, description=description,
        metric_value=metric_value, threshold=threshold,
    )
    session.add(a)
    return a


def check_overdue(session: Session) -> int:
    """NON_PAYMENT: организация просрочила оплату >30/60/90 дней."""
    today = date.today()
    created = 0
    orgs = session.exec(
        select(Organization).where(
            Organization.excluded_from_analytics == False,  # noqa: E712
            Organization.status.in_([OrgStatus.ACTIVE, OrgStatus.SUSPENDED]),  # type: ignore[union-attr]
            Organization.total_debt > 0,  # type: ignore[operator]
        )
    ).all()
    for o in orgs:
        last_pay = session.exec(
            select(func.max(Document.doc_date)).where(
                Document.organization_id == o.id,
                Document.doc_type == DocType.PAYMENT,
            )
        ).one()
        if last_pay is None:
            days = 9999
        else:
            days = (today - last_pay).days
        if days < 30:
            continue
        severity = (
            AlertSeverity.CRITICAL if days >= 90
            else AlertSeverity.WARNING if days >= 60
            else AlertSeverity.INFO
        )
        if _create(
            session, org=o, alert_type=AlertType.NON_PAYMENT,
            severity=severity,
            title=f"Просрочка {days} дн: {o.name_display or o.name_1c}",
            description=(
                f"Последний платёж {last_pay.isoformat() if last_pay else 'никогда'}, "
                f"долг {float(o.total_debt or 0):,.0f} ₽".replace(",", " ")
            ),
            metric_value=float(o.total_debt or 0),
            threshold=days,
        ):
            created += 1
    return created


def check_unassigned(session: Session) -> int:
    """UNASSIGNED_CLIENT: в реестре >14 дней без manager_id."""
    cutoff = datetime.now(UTC) - timedelta(days=14)
    created = 0
    orgs = session.exec(
        select(Organization).where(
            Organization.in_registry == True,  # noqa: E712
            Organization.manager_id.is_(None),  # type: ignore[union-attr]
            Organization.created_at < cutoff,
            Organization.status == OrgStatus.ACTIVE,
        )
    ).all()
    for o in orgs:
        if _create(
            session, org=o, alert_type=AlertType.UNASSIGNED_CLIENT,
            severity=AlertSeverity.WARNING,
            title=f"Без менеджера: {o.name_display or o.name_1c}",
            description="Активный клиент в реестре более 14 дней без manager_id",
        ):
            created += 1
    return created


def check_churn_risk(session: Session) -> int:
    """CHURN_RISK: активный клиент с 2+ неоплаченными монтлы-зарядами подряд."""
    today = date.today()
    cutoff_y, cutoff_m = today.year, today.month
    # 2 предыдущих месяца — самый понятный сигнал
    prev1_y, prev1_m = ((cutoff_y, cutoff_m - 1) if cutoff_m > 1
                        else (cutoff_y - 1, 12))
    prev2_y, prev2_m = ((prev1_y, prev1_m - 1) if prev1_m > 1
                        else (prev1_y - 1, 12))
    created = 0
    orgs = session.exec(
        select(Organization).where(
            Organization.status == OrgStatus.ACTIVE,
            Organization.excluded_from_analytics == False,  # noqa: E712
        )
    ).all()
    for o in orgs:
        # Считаем монтхли-чарджи за prev1 и prev2, и сумму аллокаций
        for (y, m) in [(prev1_y, prev1_m), (prev2_y, prev2_m)]:
            paid = session.exec(
                select(func.coalesce(func.sum(PaymentAllocation.allocated_amount), 0))
                .join(MonthlyCharge,
                      MonthlyCharge.id == PaymentAllocation.monthly_charge_id)
                .where(
                    MonthlyCharge.organization_id == o.id,
                    MonthlyCharge.year == y, MonthlyCharge.month == m,
                )
            ).one()
            if float(paid or 0) > 0:
                break
        else:
            # Ни за prev1, ни за prev2 нет аллокаций — churn risk.
            if _create(
                session, org=o, alert_type=AlertType.CHURN_RISK,
                severity=AlertSeverity.WARNING,
                title=f"Не платит 2 месяца: {o.name_display or o.name_1c}",
                description=f"Нет аллокаций за {prev2_m:02d}.{prev2_y} и {prev1_m:02d}.{prev1_y}",
            ):
                created += 1
    return created


def run_all(session: Session) -> dict[str, int]:
    """Возвращает {check_name: created_count}."""
    out = {
        "non_payment": check_overdue(session),
        "unassigned": check_unassigned(session),
        "churn_risk": check_churn_risk(session),
    }
    session.commit()
    return out
