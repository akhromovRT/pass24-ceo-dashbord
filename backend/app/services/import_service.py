import re
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import (
    Alert,
    AlertSeverity,
    AlertType,
    Contract,
    ContractStatus,
    ContractType,
    DebtSnapshot,
    DebtSnapshotLevel,
    DebtSnapshotRow,
    DocType,
    Document,
    ImportRun,
    ImportStatus,
    Organization,
    OrgStatus,
)
from app.parser.bank_statement import BankStatementResult, ParsedPayment, PaymentInfo
from app.parser.classifier import classify_contract
from app.parser.debt_report import ParsedBuyer, ParsedContract, ParsedDocument, ParseResult

_CLEAN_SUFFIXES = re.compile(
    r"[_\s]*(ДИАДОК|СБИС|_ДИАДОК|_СБИС|\(ДИАДОК\)|\(СБИС\))\s*$",
    re.IGNORECASE,
)

_DOC_TYPE_MAP = {
    "sale": DocType.SALE,
    "payment": DocType.PAYMENT,
    "correction": DocType.CORRECTION,
    "writeoff": DocType.WRITEOFF,
    "refund": DocType.REFUND,
}

_BANK_SYNTH_CONTRACT_NUMBER = "BANK-IMPORT"
_PAYMENTS_SYNTH_CONTRACT_NUMBER = "1C-PAYMENTS"


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
    from decimal import Decimal as _D  # noqa: N814

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
                select(
                    Document.doc_type, Document.doc_date, Document.doc_number, Document.amount
                ).where(Document.contract_id == contract_id)
            ).all()
            self._doc_keys_cache[contract_id] = {
                _doc_key(contract_id, dt, dd, dn, am) for dt, dd, dn, am in rows
            }
        return self._doc_keys_cache[contract_id]

    def _add_document(self, doc: Document) -> bool:
        """Идемпотентная вставка Document. True если добавлен, False если дубль."""
        key = _doc_key(doc.contract_id, doc.doc_type, doc.doc_date, doc.doc_number, doc.amount)
        keys = self._existing_doc_keys(doc.contract_id)
        if key in keys:
            self._skipped_dup_documents += 1
            return False
        self.session.add(doc)
        keys.add(key)
        return True

    def _payment_exists_in_payments_report(
        self,
        organization_id,
        doc_date,
        amount,
    ) -> bool:
        """True если в documents уже есть PAYMENT с теми же (org, date, amount)
        через synthetic-contract `1C-PAYMENTS` (реестр 1С). Защита от
        cross-source дублей при импорте банк-выписки (ADR-018)."""
        from sqlmodel import select

        from app.models import Contract

        stmt = (
            select(Document.id)
            .join(Contract, Contract.id == Document.contract_id)
            .where(
                Document.organization_id == organization_id,
                Document.doc_type == DocType.PAYMENT,
                Document.doc_date == doc_date,
                Document.amount == amount,
                Contract.contract_number == _PAYMENTS_SYNTH_CONTRACT_NUMBER,
            )
            .limit(1)
        )
        return self.session.exec(stmt).first() is not None

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
        skipped_no_inn = 0

        # Сопоставление parsed-объект → созданная сущность БД. Нужно для
        # последующего построения DebtSnapshotRow с правильными FK.
        buyer_to_org: dict[int, Organization] = {}
        contract_to_db: dict[int, Contract] = {}
        document_to_db: dict[int, Document] = {}

        for buyer in parse_result.buyers:
            # Физлица без ИНН в колонке B файла 1С — в Organization пока
            # не пишем (inn — уникальный), но в DebtSnapshot строка сохранится
            # (organization_id будет NULL). Так данные не теряются.
            if not buyer.inn:
                skipped_no_inn += 1
                continue
            org = self._process_buyer(buyer, import_run)
            buyer_to_org[id(buyer)] = org
            for parsed_contract in buyer.contracts:
                contract = self._process_contract(parsed_contract, org, import_run)
                contract_to_db[id(parsed_contract)] = contract
                contracts_count += 1
                for parsed_doc in parsed_contract.documents:
                    doc = self._build_document(parsed_doc, contract, org, import_run)
                    if self._add_document(doc):
                        documents_count += 1
                        document_to_db[id(parsed_doc)] = doc

        import_run.buyers_count = len(parse_result.buyers)
        import_run.contracts_count = contracts_count
        import_run.documents_count = documents_count
        import_run.new_buyers = self._new_buyers
        import_run.delta_summary = {
            "source": "debt_report",
            "skipped_duplicate_documents": self._skipped_dup_documents,
            "skipped_buyers_no_inn": skipped_no_inn,
        }
        import_run.status = ImportStatus.COMPLETED
        import_run.completed_at = datetime.now(UTC)

        # Полный срез 1С → DebtSnapshot + DebtSnapshotRow (этап 2).
        # Делаем ДО commit, чтобы всё легло в одной транзакции.
        self._build_debt_snapshot(
            parse_result,
            import_run,
            buyer_to_org,
            contract_to_db,
            document_to_db,
            skipped_no_inn=skipped_no_inn,
        )

        self.session.add(import_run)
        self.session.commit()
        return import_run

    def _build_document(
        self,
        parsed: ParsedDocument,
        contract: Contract,
        org: Organization,
        import_run: ImportRun,
    ) -> Document:
        """Создаёт Document без вызова _add_document (тот делает dedup)."""
        doc_type = _DOC_TYPE_MAP.get(parsed.doc_type, DocType.SALE)
        amount = parsed.amount or parsed.sold or parsed.paid or 0
        return Document(
            contract_id=contract.id,
            organization_id=org.id,
            doc_type=doc_type,
            doc_number=parsed.doc_number,
            doc_date=parsed.doc_date,
            amount=amount,
            import_run_id=import_run.id,
            raw_name=parsed.raw_name,
        )

    def _build_debt_snapshot(
        self,
        parse_result: ParseResult,
        import_run: ImportRun,
        buyer_to_org: dict,
        contract_to_db: dict,
        document_to_db: dict,
        skipped_no_inn: int,
    ) -> DebtSnapshot:
        """Сохраняет полный срез файла «Задолженность» в debt_snapshots/_rows.

        Все 8 числовых колонок сохраняются вне зависимости от того, удалось ли
        связать строку с Organization/Contract/Document. Физлица без ИНН тоже
        попадают в snapshot (organization_id остаётся NULL).
        """
        from decimal import Decimal

        def _sum(field: str) -> Decimal | None:
            """Сумма поля по всем buyer-строкам. Возвращает None только если
            ни у одного buyer это поле не заполнено (отличие от Decimal(0))."""
            total = Decimal(0)
            seen = False
            for b in parse_result.buyers:
                v = getattr(b, field, None)
                if v is not None:
                    total += v
                    seen = True
            return total if seen else None

        snapshot = DebtSnapshot(
            import_run_id=import_run.id,
            filename=parse_result.filename,
            period_start=parse_result.period_start,
            period_end=parse_result.period_end,
            total_debt_start=_sum("debt_start"),
            total_advance_start=_sum("advance_start"),
            total_sold=_sum("sold"),
            total_paid=_sum("paid"),
            total_prepay_in=_sum("prepay_in"),
            total_prepay_used=_sum("prepay_used"),
            total_debt_end=_sum("debt_end"),
            total_advance_end=_sum("advance_end"),
            buyers_count=parse_result.buyers_count,
            contracts_count=parse_result.contracts_count,
            documents_count=parse_result.documents_count,
            buyers_no_inn_count=skipped_no_inn,
        )
        self.session.add(snapshot)
        self.session.flush()

        row_index = 0
        for buyer in parse_result.buyers:
            org = buyer_to_org.get(id(buyer))
            buyer_row = DebtSnapshotRow(
                snapshot_id=snapshot.id,
                parent_row_id=None,
                level=DebtSnapshotLevel.BUYER,
                row_index=row_index,
                raw_name=buyer.name,
                raw_inn=buyer.inn or None,
                debt_start=buyer.debt_start,
                advance_start=buyer.advance_start,
                sold=buyer.sold,
                paid=buyer.paid,
                prepay_in=buyer.prepay_in,
                prepay_used=buyer.prepay_used,
                debt_end=buyer.debt_end,
                advance_end=buyer.advance_end,
                organization_id=org.id if org else None,
            )
            self.session.add(buyer_row)
            self.session.flush()
            row_index += 1

            for parsed_contract in buyer.contracts:
                contract_db = contract_to_db.get(id(parsed_contract))
                contract_row = DebtSnapshotRow(
                    snapshot_id=snapshot.id,
                    parent_row_id=buyer_row.id,
                    level=DebtSnapshotLevel.CONTRACT,
                    row_index=row_index,
                    raw_name=parsed_contract.raw_name,
                    contract_number=parsed_contract.contract_number,
                    contract_date=parsed_contract.contract_date,
                    debt_start=parsed_contract.debt_start,
                    advance_start=parsed_contract.advance_start,
                    sold=parsed_contract.sold,
                    paid=parsed_contract.paid,
                    prepay_in=parsed_contract.prepay_in,
                    prepay_used=parsed_contract.prepay_used,
                    debt_end=parsed_contract.debt_end,
                    advance_end=parsed_contract.advance_end,
                    organization_id=org.id if org else None,
                    contract_id=contract_db.id if contract_db else None,
                )
                self.session.add(contract_row)
                self.session.flush()
                row_index += 1

                for parsed_doc in parsed_contract.documents:
                    doc_db = document_to_db.get(id(parsed_doc))
                    doc_row = DebtSnapshotRow(
                        snapshot_id=snapshot.id,
                        parent_row_id=contract_row.id,
                        level=DebtSnapshotLevel.DOCUMENT,
                        row_index=row_index,
                        raw_name=parsed_doc.raw_name,
                        doc_type=parsed_doc.doc_type,
                        doc_number=parsed_doc.doc_number,
                        doc_date=parsed_doc.doc_date,
                        debt_start=parsed_doc.debt_start,
                        advance_start=parsed_doc.advance_start,
                        sold=parsed_doc.sold,
                        paid=parsed_doc.paid,
                        prepay_in=parsed_doc.prepay_in,
                        prepay_used=parsed_doc.prepay_used,
                        debt_end=parsed_doc.debt_end,
                        advance_end=parsed_doc.advance_end,
                        organization_id=org.id if org else None,
                        contract_id=contract_db.id if contract_db else None,
                        document_id=doc_db.id if doc_db else None,
                    )
                    self.session.add(doc_row)
                    row_index += 1

        return snapshot

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

            self.session.add(
                Alert(
                    organization_id=org.id,
                    alert_type=AlertType.UNASSIGNED_CLIENT,
                    severity=AlertSeverity.WARNING,
                    title=f"Новый клиент без менеджера: {cleaned_name}",
                )
            )
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

    # ---- Bank statement import ----

    def process_payments_report(
        self,
        result: BankStatementResult,
        file_hash: str,
        period_overrides: dict[int, tuple[int, int]] | None = None,
    ) -> ImportRun:
        """Импорт реестра «Оплата от покупателей» из 1С — полная история платежей.
        Документы создаются на синтетическом контракте 1C-PAYMENTS, чтобы леджер
        использовал именно этот источник."""
        return self.process_bank_import(
            result,
            file_hash,
            synthetic_contract=_PAYMENTS_SYNTH_CONTRACT_NUMBER,
            source_label="payments_report",
            period_overrides=period_overrides,
        )

    def process_bank_import(
        self,
        bank_result: BankStatementResult,
        file_hash: str,
        synthetic_contract: str = _BANK_SYNTH_CONTRACT_NUMBER,
        source_label: str = "bank_statement",
        period_overrides: dict[int, tuple[int, int]] | None = None,
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

        for idx, p in enumerate(bank_result.payments):
            # Применить ручной оверрайд периода
            if period_overrides and idx in period_overrides:
                year, month = period_overrides[idx]
                if p.payment_info is None:
                    p.payment_info = PaymentInfo()
                p.payment_info.period_year = year
                p.payment_info.period_month = month
                p.payment_info.periods = [(year, month)]
                p.payment_info.period_manual = True

            inn = _normalize_inn(p.inn)
            if not inn:
                skipped_no_inn += 1
                errors.append(
                    {
                        "type": "no_inn",
                        "date": str(p.date),
                        "amount": float(p.amount),
                        "counterparty": p.counterparty,
                    }
                )
                continue
            if len(inn) not in (10, 12):
                errors.append(
                    {
                        "type": "invalid_inn_length",
                        "inn": inn,
                        "len": len(inn),
                        "date": str(p.date),
                        "counterparty": p.counterparty,
                    }
                )
                continue

            org = self._find_or_create_org_from_bank(p, inn)
            contract = self._get_or_create_synth_contract(org, synthetic_contract)
            if org.id not in seen_orgs:
                seen_orgs.add(org.id)
            if contract.id not in seen_contracts:
                seen_contracts.add(contract.id)
                contracts_count += 1

            # Cross-source dedup (ADR-018, профилактика): не создавать
            # bank-документ, если в documents уже есть платёж из реестра 1С
            # (payments.xls / 1C-PAYMENTS) с теми же (org, date, amount).
            # Реестр 1С — source of truth, банк — копия.
            if self._payment_exists_in_payments_report(org.id, p.date, p.amount):
                self._skipped_dup_documents += 1
                continue

            doc = Document(
                contract_id=contract.id,
                organization_id=org.id,
                doc_type=DocType.PAYMENT,
                doc_number=p.doc_number or None,
                doc_date=p.date,
                amount=p.amount,
                period_year=p.payment_info.period_year if p.payment_info else None,
                period_month=p.payment_info.period_month if p.payment_info else None,
                period_manual=p.payment_info.period_manual if p.payment_info else False,
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
            "source": source_label,
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

        # Пересчёт AR-леджера для затронутых клиентов
        from app.services.allocation_service import AllocationService

        alloc_svc = AllocationService(self.session)
        for affected_org_id in seen_orgs:
            alloc_svc.recompute_for_organization(affected_org_id)

        self.session.commit()
        return import_run

    def _find_or_create_org_from_bank(self, p: ParsedPayment, inn: str) -> Organization:
        org = self.session.exec(select(Organization).where(Organization.inn == inn)).first()
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

        self.session.add(
            Alert(
                organization_id=org.id,
                alert_type=AlertType.UNASSIGNED_CLIENT,
                severity=AlertSeverity.WARNING,
                title=f"Новый клиент из банк-выписки: {name}",
            )
        )
        return org

    def _get_or_create_synth_contract(self, org: Organization, contract_number: str) -> Contract:
        existing = self.session.exec(
            select(Contract).where(
                Contract.organization_id == org.id,
                Contract.contract_number == contract_number,
            )
        ).first()
        if existing:
            return existing

        contract = Contract(
            organization_id=org.id,
            contract_number=contract_number,
            contract_type=ContractType.OTHER,
            classification_source="payment_import",
            classification_rule="synthetic",
            raw_name="Синтетический контракт для платежей без привязки к договору 1С",
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
            org = self.session.exec(select(Organization).where(Organization.inn == inn)).first()
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
                self.session.add(
                    Alert(
                        organization_id=org.id,
                        alert_type=AlertType.UNASSIGNED_CLIENT,
                        severity=AlertSeverity.WARNING,
                        title=f"Новый клиент из реестра: {comp.company_name}",
                    )
                )

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
                    for attr in (
                        "cloud_url",
                        "object_number",
                        "object_type",
                        "address",
                        "city_region",
                    ):
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
