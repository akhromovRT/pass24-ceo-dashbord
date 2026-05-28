"""Извлечение периода(ов) оплаты из назначения банковского платежа."""

import re
from dataclasses import dataclass, field
from datetime import date

_MIN_YEAR = 2019


def _max_year() -> int:
    return date.today().year + 1


# Slash-формат ДД/ГГГГ. Negative lookbehind/lookahead — чтобы не цеплять
# даты внутри номеров договоров ("1083-09/2020").
_SLASH_RE = re.compile(r"(?<![\d/\-.])(\d{1,2})\s*/\s*(20\d{2})(?![\d/])")

# Формат "MM.YYYY" с точкой: "ЗА 05.2026Г"
# Lookbehind (?<![\d/\-.]) — не матчим внутри "20.04.2026" (перед 04 стоит точка)
# Lookahead (?![\d/.]) — не матчим внутри цепочек дат
_DOT_RE = re.compile(r"(?<![\d/\-.])(\d{1,2})\s*\.\s*(20\d{2})(?![\d/.])")

_MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "мая": 5,
    "май": 5,
    "мае": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
_MONTH_NAME_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")[а-яё]*\s*(20\d{2})?",
    re.IGNORECASE,
)
_RANGE_RE = re.compile(
    r"\b(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")[а-яё]*\s*[-–—]\s*"
    r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")[а-яё]*\s*(20\d{2})",
    re.IGNORECASE,
)
_COVERAGE_RE = re.compile(r"(?:за|на)\s+(\d{1,2})\s+месяц|на\s+(полгода)|на\s+(год)", re.IGNORECASE)

_SUBSCRIPTION_HINTS = ("доступ", "pass24", "абонент", "сервис", "лицензи")
_OTHER_HINTS = ("оборудовани", "монтаж", "поставк", "установк", "пусконаладк")


@dataclass
class ExtractedPeriods:
    periods: list[tuple[int, int]] = field(default_factory=list)
    coverage_months: int | None = None
    payment_kind: str = "subscription"  # subscription | other


def _valid(year: int, month: int) -> bool:
    return _MIN_YEAR <= year <= _max_year() and 1 <= month <= 12


def _infer_year(month: int, doc_date: date) -> int:
    """Год, при котором (year, month) ближе всего к дате платежа."""
    candidates = [doc_date.year - 1, doc_date.year, doc_date.year + 1]
    ref = doc_date.year * 12 + doc_date.month
    return min(candidates, key=lambda y: abs((y * 12 + month) - ref))


def _month_from_stem(stem: str) -> int | None:
    stem = stem.lower()
    return next((v for k, v in _MONTHS.items() if stem.startswith(k)), None)


def extract_periods(description: str, doc_date: date) -> ExtractedPeriods:
    text = description or ""
    result = ExtractedPeriods()
    found: set[tuple[int, int]] = set()

    # Slash-формат "03/2026"
    for m in _SLASH_RE.finditer(text):
        month, year = int(m.group(1)), int(m.group(2))
        if _valid(year, month):
            found.add((year, month))

    # Точечный формат "05.2026" / "05.2026Г"
    for m in _DOT_RE.finditer(text):
        month, year = int(m.group(1)), int(m.group(2))
        if _valid(year, month):
            found.add((year, month))

    # Диапазоны "январь-июнь 2026"
    for m in _RANGE_RE.finditer(text):
        m1 = _month_from_stem(m.group(1))
        m2 = _month_from_stem(m.group(2))
        year = int(m.group(3))
        if m1 and m2 and _valid(year, m1) and _valid(year, m2) and m1 <= m2:
            for mm in range(m1, m2 + 1):
                found.add((year, mm))

    # Одиночные месяцы по названию
    if not found:
        for m in _MONTH_NAME_RE.finditer(text):
            month = _month_from_stem(m.group(1))
            if month is None:
                continue
            year = int(m.group(2)) if m.group(2) else _infer_year(month, doc_date)
            if _valid(year, month):
                found.add((year, month))

    # Количество месяцев без названных
    if not found:
        cov = _COVERAGE_RE.search(text)
        if cov:
            if cov.group(1):
                result.coverage_months = int(cov.group(1))
            elif cov.group(2):
                result.coverage_months = 6
            elif cov.group(3):
                result.coverage_months = 12

    result.periods = sorted(found)

    # Классификация платежа
    low = text.lower()
    if any(h in low for h in _OTHER_HINTS) and not any(h in low for h in _SUBSCRIPTION_HINTS):
        result.payment_kind = "other"

    return result
