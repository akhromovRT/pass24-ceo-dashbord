import re
from datetime import UTC, datetime

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import (
    Alert, AlertSeverity, AlertType,
    Contract, ContractStatus, ContractType,
    Document, DocType,
    ImportRun, ImportStatus,
    Organization, OrgStatus,
)
from app.parser.bank_statement import BankStatementResult, ParsedPayment
from app.parser.classifier import classify_contract
from app.parser.debt_report import ParsedBuyer, ParsedContract, ParsedDocument, ParseResult

_CLEAN_SUFFIXES = re.compile(
    r"[_\s]*(ДИАДОК|СБИС|_ДИАДОК|_СБИС|\(ДИАДОК\)|\(СБИС\))\s*$",
    re.IGNORECASE,
)

_DOC_TYPE_MAP = {
    "sale": DocType.SALE,
    "payment": DocType.PAYMENT,
}

_BANK_SYNTH_CONTRACT_NUMBER = "BANK-IMPORT"


def _clean_name(name: str) -> str:
    return _CLEAN_SUFFIXES.sub("", name).strip()


def _normalize_inn(inn: str) -> str:
    s = (inn or "").strip()
    if not s:
        return ""
    if len(s) == 9:
        return s.zfill(10)
    if len(s) == 11:
        return s.zfill(12)
    return s


def _doc_key(contract_id, doc_type, doc_date, doc_number, amount):
    """Канонический ключ для дедупликации Document.
    Сумма нормализуется до 2 знаков после запятой, чтобы Decimal('7000')
    и Decimal('7000.00') давали один и тот же ключ."""
    from decimal import Decimal as _D
    try:
        amt = _D(str(amount or 0))
    except Exception:
        amt = _D(0)
    return (
        str(contract_id),
        str(doc_type.value if hasattr(doc_type, "value") else doc_type),
        str(doc_date) if doc_date else "",
        (doc_number or "").strip(),
        f"{amt:.2f}",
    )


class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self._new_buyers = 0
        # Cache existing document keys per contract — populated lazily
        self._doc_keys_cache: dict = {}
        self._skipped_dup_documents = 0

    # ---- Document dedup helper ----

    def _existing_doc_keys(self, contract_id) -> set:
        """Возвращает set ключей существующих Document для контракта.
        Кешируется по contract_id (BLOB queries × 1, не × N документов)."""
        if contract_id not in self._doc_keys_cache:
            rows = self.session.exec(
                select(Document.doc_type, Document.doc_date,
                       Document.doc_number, Document.amount)
                .where(Document.contract_id == contract_id)
            ).all()
            self._doc_keys_cache[contract_id] = {
                _doc_key(contract_id, dt, dd, dn, am)
                for dt, dd, dn, am in rows
            }
        return self._doc_keys_cache[contract_id]

    def _add_document(self, doc: Document) -> bool:
        """Идемпотентная вставка Document. True если добавлен, False если дубль."""
        key = _doc_key(doc.contract_id, doc.doc_type, doc.doc_date,
                       doc.doc_number, doc.amount)
        keys = self._existing_doc_keys(doc.contract_id)
        if key in keys:
            self._skipped_dup_documents += 1
            return False
        self.session.add(doc)
        keys.add(key)
        return True

    # ---- Debt-report import ----

    def process_import(self, parse_result: ParseResult) -> ImportRun:
        self._new_buyers = 0
        self._skipped_dup_documents = 0
        self._doc_keys_cache = {}

        import_run = ImportRun(
            filename=parse_result.filename,
            file_hash=parse_result.file_hash,
            period_start=parse_result.period_start,
            period_end=parse_result.period_end,
            status=ImportStatus.PROCESSING,
            total_rows=parse_result.total_rows,
        )
        self.session.add(import_run)
        self.session.flush()

        contracts_count = 0
        documents_count = 0

        for buyer in parse_result.buyers:
            org = self._process_buyer(buyer, import_run)
            for parsed_contract in buyer.contracts:
                contract = self._process_contract(parsed_contract, org, import_run)
                contracts_count += 1
                for parsed_doc in parsed_contract.documents:
                    if self._process_document(parsed_doc, contract, org, import_run):
                        documents_count += 1

        import_run.buyers_count = len(parse_result.buyers)
        import_run.contracts_count = contracts_count
        import_run.documents_count = documents_count
        import_run.new_buyers = self._new_buyers
        import_run.delta_summary = {
            "source": "debt_report",
            "skipped_duplicate_documents": self._skipped_dup_documents,
        }
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)

        self.session.add(import_run)
        self.session.commit()
        return import_run

    def _process_buyer(self, buyer: ParsedBuyer, import_run: ImportRun) -> Organization:
        normalized_inn = _normalize_inn(buyer.inn)
        org = self.session.exec(
            select(Organization).where(Organization.inn == normalized_inn)
        ).first()

        if org is None:
            cleaned_name = _clean_name(buyer.name)
            org = Organization(
                inn=normalized_inn,
                name_1c=cleaned_name,
                total_debt=buyer.debt_end,
            )
            self.session.add(org)
            self.session.flush()
            self._new_buyers += 1

            self.session.add(Alert(
                organization_id=org.id,
                alert_type=AlertType.UNASSIGNED_CLIENT,
                severity=AlertSeverity.WARNING,
                title=f"Новый клиент без менеджера: {cleaned_name}",
            ))
        else:
            org.total_debt = buyer.debt_end
            self.session.add(org)

        return org

    def _process_contract(
        self, parsed: ParsedContract, org: Organization, import_run: ImportRun
    ) -> Contract:
        existing = None
        if parsed.contract_number:
            existing = self.session.exec(
                select(Contract).where(
                    Contract.organization_id == org.id,
                    Contract.contract_number == parsed.contract_number,
                )
            ).first()

        if existing:
            return existing

        classification = classify_contract(parsed.raw_name)
        contract = Contract(
            organization_id=org.id,
            contract_number=parsed.contract_number,
            contract_date=parsed.contract_date,
            contract_type=classification.type,
            classification_source=classification.source,
            classification_rule=classification.rule,
            raw_name=parsed.raw_name,
            status=ContractStatus.ACTIVE,
        )
        self.session.add(contract)
        self.session.flush()
        return contract

    def _process_document(
        self,
        parsed: ParsedDocument,
        contract: Contract,
        org: Organization,
        import_run: ImportRun,
    ) -> bool:
        doc_type = _DOC_TYPE_MAP.get(parsed.doc_type, DocType.SALE)
        amount = parsed.amount or parsed.sold or parsed.paid or 0

        doc = Document(
            contract_id=contract.id,
            organization_id=org.id,
            doc_type=doc_type,
            doc_number=parsed.doc_number,
            doc_date=parsed.doc_date,
            amount=amount,
            import_run_id=import_run.id,
            raw_name=parsed.raw_name,
        )
        return self._add_document(doc)

    # ---- Bank statement import ----

    def process_bank_import(
        self,
        bank_result: BankStatementResult,
        file_hash: str,
    ) -> ImportRun:
        self._new_buyers = 0
        self._skipped_dup_documents = 0
        self._doc_keys_cache = {}

        period_dates = [p.date for p in bank_result.payments]
        period_start = min(period_dates) if period_dates else None
        period_end = max(period_dates) if period_dates else None

        import_run = ImportRun(
            filename=bank_result.filename,
            file_hash=file_hash,
            period_start=period_start,
            period_end=period_end,
            status=ImportStatus.PROCESSING,
            total_rows=len(bank_result.payments),
        )
        self.session.add(import_run)
        self.session.flush()

        documents_count = 0
        contracts_count = 0
        skipped_no_inn = 0
        errors: list[dict] = []
        seen_orgs: set = set()
        seen_contracts: set = set()

        for p in bank_result.payments:
            inn = _normalize_inn(p.inn)
            if not inn:
                skipped_no_inn += 1
                errors.append({
                    "type": "no_inn",
                    "date": str(p.date),
                    "amount": float(p.amount),
                    "counterparty": p.counterparty,
                })
                continue
            if len(inn) not in (10, 12):
                errors.append({
                    "type": "invalid_inn_length",
                    "inn": inn,
                    "len": len(inn),
                    "date": str(p.date),
                    "counterparty": p.counterparty,
                })
                continue

            org = self._find_or_create_org_from_bank(p, inn)
            contract = self._get_or_create_bank_contract(org)
            if org.id not in seen_orgs:
                seen_orgs.add(org.id)
            if contract.id not in seen_contracts:
                seen_contracts.add(contract.id)
                contracts_count += 1

            doc = Document(
                contract_id=contract.id,
                organization_id=org.id,
                doc_type=DocType.PAYMENT,
                doc_number=p.doc_number or None,
                doc_date=p.date,
                amount=p.amount,
                period_year=p.payment_info.period_year if p.payment_info else None,
                period_month=p.payment_info.period_month if p.payment_info else None,
                import_run_id=import_run.id,
                raw_name=(p.description or "")[:500],
            )
            if self._add_document(doc):
                documents_count += 1

        import_run.buyers_count = len(seen_orgs)
        import_run.contracts_count = contracts_count
        import_run.documents_count = documents_count
        import_run.new_buyers = self._new_buyers
        import_run.errors = errors or None
        import_run.delta_summary = {
            "source": "bank_statement",
            "account_number": bank_result.account_number,
            "owner": bank_result.owner,
            "period_raw": bank_result.period,
            "total_payments": len(bank_result.payments),
            "skipped_no_inn": skipped_no_inn,
            "skipped_duplicate_documents": self._skipped_dup_documents,
        }
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)
        self.session.add(import_run)
        self.session.commit()
        return import_run

    def _find_or_create_org_from_bank(self, p: ParsedPayment, inn: str) -> Organization:
        org = self.session.exec(
            select(Organization).where(Organization.inn == inn)
        ).first()
        if org is not None:
            return org

        name = (p.counterparty or "").strip()
        name = re.split(r"\s+Р/С\s+", name, maxsplit=1)[0].strip()
        name = name[:255] or f"Компания ИНН {inn}"

        org = Organization(
            inn=inn,
            name_1c=name,
            status=OrgStatus.PROSPECT,
        )
        self.session.add(org)
        self.session.flush()
        self._new_buyers += 1

        self.session.add(Alert(
            organization_id=org.id,
            alert_type=AlertType.UNASSIGNED_CLIENT,
            severity=AlertSeverity.WARNING,
            title=f"Новый клиент из банк-выписки: {name}",
        ))
        return org

    def _get_or_create_bank_contract(self, org: Organization) -> Contract:
        existing = self.session.exec(
            select(Contract).where(
                Contract.organization_id == org.id,
                Contract.contract_number == _BANK_SYNTH_CONTRACT_NUMBER,
            )
        ).first()
        if existing:
            return existing

        contract = Contract(
            organization_id=org.id,
            contract_number=_BANK_SYNTH_CONTRACT_NUMBER,
            contract_type=ContractType.OTHER,
            classification_source="bank_import",
            classification_rule="synthetic",
            raw_name="Платежи из банк-выписки без привязки к договору 1С",
            status=ContractStatus.ACTIVE,
        )
        self.session.add(contract)
        self.session.flush()
        return contract

    # ---- Registry (Клиентская база) import ----

    def process_registry_import(
        self,
        result,  # RegistryParseResult
        file_hash: str,
    ):
        """Импорт реестра. Идемпотентен: повторный импорт того же файла даст
        409 по file_hash. ClientObject upsert делается по case-insensitive
        ключу (organization_id, LOWER(name)) — поэтому даже при изменении
        регистра букв дубль не создастся."""
        from app.models import ClientObject

        self._new_buyers = 0

        import_run = ImportRun(
            filename=result.filename,
            file_hash=file_hash,
            status=ImportStatus.PROCESSING,
            total_rows=result.total_rows,
        )
        self.session.add(import_run)
        self.session.flush()

        orgs_marked = 0
        orgs_created = 0
        objects_added = 0
        objects_updated = 0
        objects_dedup_skipped = 0

        for comp in result.companies:
            inn = _normalize_inn(comp.inn)
            org = self.session.exec(
                select(Organization).where(Organization.inn == inn)
            ).first()
            if org is None:
                org = Organization(
                    inn=inn,
                    name_1c=_clean_name(comp.company_name)[:255],
                    status=OrgStatus.PROSPECT,
                )
                self.session.add(org)
                self.session.flush()
                self._new_buyers += 1
                orgs_created += 1
                self.session.add(Alert(
                    organization_id=org.id,
                    alert_type=AlertType.UNASSIGNED_CLIENT,
                    severity=AlertSeverity.WARNING,
                    title=f"Новый клиент из реестра: {comp.company_name}",
                ))

            org.in_registry = True
            if comp.contract_1c:
                org.contract_1c_raw = comp.contract_1c
            if comp.active_doc:
                org.active_doc_raw = comp.active_doc
            if comp.objects_count_declared is not None:
                org.objects_count_declared = comp.objects_count_declared
            if comp.doc_exchange:
                org.doc_exchange = comp.doc_exchange

            if comp.objects:
                first = comp.objects[0]
                if first.cloud_url and not org.cloud_url:
                    org.cloud_url = first.cloud_url
                if first.object_number and not org.system_number:
                    org.system_number = first.object_number
                if first.object_type and not org.object_type:
                    org.object_type = first.object_type
                if first.address and not org.address:
                    org.address = first.address
                if first.city_region and not org.city_region:
                    org.city_region = first.city_region

            org.updated_at = datetime.now(UTC)
            self.session.add(org)
            self.session.flush()
            orgs_marked += 1

            # Upsert ClientObject by case-insensitive name
            existing_by_lname: dict = {}
            for o in self.session.exec(
                select(ClientObject).where(ClientObject.organization_id == org.id)
            ).all():
                key = o.name.strip().lower()
                if key in existing_by_lname:
                    # In-DB duplicate detected — keep first, will be cleaned up by dedupe script
                    objects_dedup_skipped += 1
                    continue
                existing_by_lname[key] = o

            for parsed_obj in comp.objects:
                key = parsed_obj.name.strip().lower()
                obj = existing_by_lname.get(key)
                if obj is None:
                    obj = ClientObject(
                        organization_id=org.id,
                        name=parsed_obj.name[:255],
                        cloud_url=parsed_obj.cloud_url,
                        object_number=parsed_obj.object_number,
                        object_type=parsed_obj.object_type,
                        address=parsed_obj.address,
                        city_region=parsed_obj.city_region,
                    )
                    self.session.add(obj)
                    existing_by_lname[key] = obj
                    objects_added += 1
                else:
                    changed = False
                    for attr in ("cloud_url", "object_number", "object_type", "address", "city_region"):
                        new_val = getattr(parsed_obj, attr)
                        if new_val and getattr(obj, attr) != new_val:
                            setattr(obj, attr, new_val)
                            changed = True
                    if changed:
                        obj.updated_at = datetime.now(UTC)
                        self.session.add(obj)
                        objects_updated += 1

        import_run.buyers_count = orgs_marked
        import_run.contracts_count = 0
        import_run.documents_count = objects_added + objects_updated
        import_run.new_buyers = orgs_created
        import_run.errors = result.skipped_no_inn or None
        import_run.delta_summary = {
            "source": "registry",
            "orgs_marked_in_registry": orgs_marked,
            "orgs_created": orgs_created,
            "objects_added": objects_added,
            "objects_updated": objects_updated,
            "objects_dedup_skipped_in_db": objects_dedup_skipped,
            "skipped_no_inn": len(result.skipped_no_inn),
        }
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)
        self.session.add(import_run)
        self.session.commit()
        return import_run
