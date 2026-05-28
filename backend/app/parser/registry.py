"""Парсер «Клиентская база» — реестр компаний с объектами.

Формат: Excel с шапкой на строке 3, данные с строки 4.
Столбцы: №, Компания, Объект, ИНН, Договор 1С, Активный документ,
         Ссылка на облако, № объекта в облаке, Количество объектов,
         Тип объекта, Адрес, Город/область, ...

Одна компания может иметь несколько строк — каждая строка = отдельный
объект (ЖК / КП / БЦ). Группировка по ИНН.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.parser.utils import load_workbook_any

_HEADER_ROW = 3
_FIRST_DATA_ROW = 4

# 1-based column indices according to the sheet layout
_COL = {
    "company": 2,
    "object_name": 3,
    "inn": 4,
    "contract_1c": 5,
    "active_doc": 6,
    "cloud_url": 7,
    "object_number": 8,
    "objects_count": 9,
    "object_type": 10,
    "address": 11,
    "city_region": 12,
    "doc_exchange": 13,
}


@dataclass
class ParsedRegistryObject:
    name: str
    cloud_url: str | None = None
    object_number: str | None = None
    object_type: str | None = None
    address: str | None = None
    city_region: str | None = None


@dataclass
class ParsedRegistryCompany:
    inn: str
    company_name: str
    contract_1c: str | None = None
    active_doc: str | None = None
    objects_count_declared: int | None = None
    doc_exchange: str | None = None
    objects: list[ParsedRegistryObject] = field(default_factory=list)


@dataclass
class RegistryParseResult:
    filename: str
    companies: list[ParsedRegistryCompany] = field(default_factory=list)
    skipped_no_inn: list[dict] = field(default_factory=list)
    total_rows: int = 0


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _normalize_inn(s: str | None) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # Excel may have stored INN as integer — pad leading zeros
    if len(s) == 9:
        return s.zfill(10)
    if len(s) == 11:
        return s.zfill(12)
    return s


def parse_registry(file_path: str | Path) -> RegistryParseResult:
    file_path = Path(file_path)
    wb = load_workbook_any(file_path)
    # The data sheet may not be the active one
    ws = None
    for sheet_name in wb.sheetnames:
        s = wb[sheet_name]
        header_b = s.cell(row=_HEADER_ROW, column=_COL["company"]).value
        if header_b and str(header_b).strip().lower() == "компания":
            ws = s
            break
    if ws is None:
        ws = wb.active

    result = RegistryParseResult(filename=file_path.name)

    by_inn: dict[str, ParsedRegistryCompany] = {}

    for r in range(_FIRST_DATA_ROW, ws.max_row + 1):
        company = _clean(ws.cell(row=r, column=_COL["company"]).value)
        object_name = _clean(ws.cell(row=r, column=_COL["object_name"]).value)
        raw_inn = ws.cell(row=r, column=_COL["inn"]).value
        # Excel often stores INN as int — convert to string
        if isinstance(raw_inn, (int, float)):
            inn_str = str(int(raw_inn))
        else:
            inn_str = _clean(raw_inn) or ""
        inn = _normalize_inn(inn_str)

        # Skip fully empty rows
        if not company and not object_name and not inn:
            continue

        result.total_rows += 1

        if not inn:
            result.skipped_no_inn.append(
                {
                    "row": r,
                    "company": company,
                    "object_name": object_name,
                }
            )
            continue

        if len(inn) not in (10, 12):
            result.skipped_no_inn.append(
                {
                    "row": r,
                    "company": company,
                    "object_name": object_name,
                    "reason": f"invalid_inn_length={len(inn)}",
                    "inn": inn,
                }
            )
            continue

        # Get or create company entry
        comp = by_inn.get(inn)
        if comp is None:
            objects_count = ws.cell(row=r, column=_COL["objects_count"]).value
            try:
                objects_count_int = int(objects_count) if objects_count is not None else None
            except (ValueError, TypeError):
                objects_count_int = None

            comp = ParsedRegistryCompany(
                inn=inn,
                company_name=company or f"Компания ИНН {inn}",
                contract_1c=_clean(ws.cell(row=r, column=_COL["contract_1c"]).value),
                active_doc=_clean(ws.cell(row=r, column=_COL["active_doc"]).value),
                objects_count_declared=objects_count_int,
                doc_exchange=_clean(ws.cell(row=r, column=_COL["doc_exchange"]).value),
            )
            by_inn[inn] = comp

        # Add object (if has a name). Dedup within a single company by
        # (normalized name, normalized cloud_url) — a duplicated row in the
        # source file (same name + same cloud URL) is just paste noise.
        if object_name:
            obj = ParsedRegistryObject(
                name=object_name,
                cloud_url=_clean(ws.cell(row=r, column=_COL["cloud_url"]).value),
                object_number=_clean(ws.cell(row=r, column=_COL["object_number"]).value),
                object_type=_clean(ws.cell(row=r, column=_COL["object_type"]).value),
                address=_clean(ws.cell(row=r, column=_COL["address"]).value),
                city_region=_clean(ws.cell(row=r, column=_COL["city_region"]).value),
            )
            sig = (object_name.strip().lower(), (obj.cloud_url or "").strip().lower())
            if any(
                (o.name.strip().lower(), (o.cloud_url or "").strip().lower()) == sig
                for o in comp.objects
            ):
                continue  # duplicate row in source file — skip
            comp.objects.append(obj)

    result.companies = list(by_inn.values())
    wb.close()
    return result
