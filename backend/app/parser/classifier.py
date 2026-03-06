from dataclasses import dataclass
from app.models.contract import ContractType


SUBSCRIPTION_KEYWORDS = ["/П", "/P", "услуг", "оказан", "абонент", "обслужив"]
EQUIPMENT_KEYWORDS = ["монтаж", "поставк", "оборудов", "установк", "СКУД", "ГРЗ"]
SERVICE_KEYWORDS = ["ремонт", "техобслуж", "сервис"]

AMOUNT_THRESHOLD = 100_000


@dataclass
class ClassificationResult:
    type: ContractType
    rule: str
    source: str = "auto"


def classify_contract(
    name: str, single_amount: float | None = None
) -> ClassificationResult:
    name_upper = name.upper()

    for kw in SUBSCRIPTION_KEYWORDS:
        if kw.upper() in name_upper:
            return ClassificationResult(
                type=ContractType.SUBSCRIPTION,
                rule=f"keyword: {kw}",
            )

    for kw in EQUIPMENT_KEYWORDS:
        if kw.upper() in name_upper:
            return ClassificationResult(
                type=ContractType.EQUIPMENT,
                rule=f"keyword: {kw}",
            )

    for kw in SERVICE_KEYWORDS:
        if kw.upper() in name_upper:
            return ClassificationResult(
                type=ContractType.SERVICE,
                rule=f"keyword: {kw}",
            )

    if single_amount is not None and single_amount >= AMOUNT_THRESHOLD:
        return ClassificationResult(
            type=ContractType.EQUIPMENT,
            rule=f"amount >= {AMOUNT_THRESHOLD}",
        )

    return ClassificationResult(
        type=ContractType.OTHER,
        rule="no match",
    )
