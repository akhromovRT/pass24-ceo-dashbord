import re
from datetime import UTC, datetime
from decimal import Decimal

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


class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self._new_buyers = 0

    def process_import(self, parse_result: ParseResult) -> ImportRun:
        self._new_buyers = 0

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
                    self._process_document(parsed_doc, contract, org, import_run)
                    documents_count += 1

        import_run.buyers_count = len(parse_result.buyers)
        import_run.contracts_count = contracts_count
        import_run.documents_count = documents_count
        import_run.new_buyers = self._new_buyers
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)

        self.session.add(import_run)
        self.session.commit()
        return import_run

    def _process_buyer(self, buyer: ParsedBuyer, import_run: ImportRun) -> Organization:
        org = self.session.exec(
            select(Organization).where(Organization.inn == buyer.inn)
        ).first()

        if org is None:
            cleaned_name = _clean_name(buyer.name)
            org = Organization(
                inn=buyer.inn,
                name_1c=cleaned_name,
                total_debt=buyer.debt_end,
            )
            self.session.add(org)
            self.session.flush()
            self._new_buyers += 1

            alert = Alert(
                organization_id=org.id,
                alert_type=AlertType.UNASSIGNED_CLIENT,
                severity=AlertSeverity.WARNING,
                title=f"Новый клиент без менеджера: {cleaned_name}",
            )
            self.session.add(alert)
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
    ) -> Document:
        doc_type = _DOC_TYPE_MAP.get(parsed.doc_type, DocType.SALE)

        doc = Document(
            contract_id=contract.id,
            organization_id=org.id,
            doc_type=doc_type,
            doc_number=parsed.doc_number,
            doc_date=parsed.doc_date,
            amount=parsed.amount or parsed.sold or parsed.paid or 0,
            import_run_id=import_run.id,
            raw_name=parsed.raw_name,
        )
        self.session.add(doc)
        return doc

    # ---- Bank statement import ----

    def process_bank_import(
        self,
        bank_result: BankStatementResult,
        file_hash: str,
    ) -> ImportRun:
        """Импорт банковской выписки: каждый платёж — Document(doc_type=PAYMENT).
        Привязка к Organization по нормализованному ИНН. Если организации нет —
        создаём со status=PROSPECT. Каждой организации заводится синтетический
        контракт BANK-IMPORT, если он не существует — туда привязываются все
        bank-импорт документы (не путать с реальными контрактами из 1С)."""

        self._new_buyers = 0

        # Период
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
            # Sanity check: INN length must be 10 or 12
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
            self.session.add(doc)
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
        # Bank counterparty часто содержит "Р/С..." после имени — отсекаем
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

        alert = Alert(
            organization_id=org.id,
            alert_type=AlertType.UNASSIGNED_CLIENT,
            severity=AlertSeverity.WARNING,
            title=f"Новый клиент из банк-выписки: {name}",
        )
        self.session.add(alert)
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
        """Импорт реестра «Клиентская база»: для каждой компании по ИНН
        проставляем in_registry=True и переносим/обогащаем поля. Объекты
        складываем в client_objects (multi-object support)."""
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
        for comp in result.companies:
            org = self.session.exec(
                select(Organization).where(Organization.inn == comp.inn)
            ).first()
            if org is None:
                org = Organization(
                    inn=comp.inn,
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

            # Mark in registry + transfer org-level fields
            org.in_registry = True
            if comp.contract_1c:
                org.contract_1c_raw = comp.contract_1c
            if comp.active_doc:
                org.active_doc_raw = comp.active_doc
            if comp.objects_count_declared is not None:
                org.objects_count_declared = comp.objects_count_declared

            # For back-compat with existing UI fields (single-object snapshot)
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

            # Sync ClientObject rows: upsert by (organization_id, name)
            existing_objects = {
                o.name: o for o in self.session.exec(
                    select(ClientObject).where(ClientObject.organization_id == org.id)
                ).all()
            }
            for parsed_obj in comp.objects:
                obj = existing_objects.get(parsed_obj.name)
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
            "skipped_no_inn": len(result.skipped_no_inn),
        }
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)
        self.session.add(import_run)
        self.session.commit()
        return import_run
