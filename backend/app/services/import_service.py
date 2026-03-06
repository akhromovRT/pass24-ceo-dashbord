import re
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import (
    Alert, AlertSeverity, AlertType,
    Contract, ContractStatus,
    Document, DocType,
    ImportRun, ImportStatus,
    Organization,
)
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


def _clean_name(name: str) -> str:
    return _CLEAN_SUFFIXES.sub("", name).strip()


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
