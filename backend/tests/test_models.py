from decimal import Decimal

from app.models.organization import OrgStatus, OrgType, Organization
from app.models.contract import Contract, ContractStatus, ContractType
from app.models.document import DocType, Document


class TestOrganization:
    def test_create_organization(self):
        org = Organization(
            inn="9717053891",
            name_1c='ООО "7 НЕБО"',
            name_display="7 НЕБО",
            org_type=OrgType.OOO,
            status=OrgStatus.ACTIVE,
            monthly_ap=Decimal("15000.00"),
        )
        assert org.inn == "9717053891"
        assert org.name_1c == 'ООО "7 НЕБО"'
        assert org.name_display == "7 НЕБО"
        assert org.org_type == OrgType.OOO
        assert org.status == OrgStatus.ACTIVE
        assert org.monthly_ap == Decimal("15000.00")

    def test_default_status_is_active(self):
        org = Organization(inn="1234567890", name_1c="Test")
        assert org.status == OrgStatus.ACTIVE

    def test_optional_fields_default_none(self):
        org = Organization(inn="1234567890", name_1c="Test")
        assert org.name_display is None
        assert org.org_type is None
        assert org.monthly_ap is None
        assert org.total_debt is None
        assert org.payment_score is None


class TestContract:
    def test_create_contract(self):
        import uuid

        org_id = uuid.uuid4()
        contract = Contract(
            organization_id=org_id,
            contract_number="Д-123",
            contract_type=ContractType.SUBSCRIPTION,
            monthly_amount=Decimal("5000.00"),
            status=ContractStatus.ACTIVE,
            raw_name="Договор №Д-123 от 01.01.2025",
        )
        assert contract.organization_id == org_id
        assert contract.contract_number == "Д-123"
        assert contract.contract_type == ContractType.SUBSCRIPTION
        assert contract.monthly_amount == Decimal("5000.00")
        assert contract.status == ContractStatus.ACTIVE

    def test_default_type_is_other(self):
        import uuid

        contract = Contract(organization_id=uuid.uuid4())
        assert contract.contract_type == ContractType.OTHER

    def test_default_status_is_active(self):
        import uuid

        contract = Contract(organization_id=uuid.uuid4())
        assert contract.status == ContractStatus.ACTIVE


class TestDocument:
    def test_create_document(self):
        import uuid

        contract_id = uuid.uuid4()
        org_id = uuid.uuid4()
        doc = Document(
            contract_id=contract_id,
            organization_id=org_id,
            doc_type=DocType.SALE,
            amount=Decimal("25000.00"),
            doc_number="РЛ-001",
            period_year=2026,
            period_month=1,
        )
        assert doc.contract_id == contract_id
        assert doc.organization_id == org_id
        assert doc.doc_type == DocType.SALE
        assert doc.amount == Decimal("25000.00")
        assert doc.doc_number == "РЛ-001"
        assert doc.period_year == 2026
        assert doc.period_month == 1

    def test_all_doc_types(self):
        import uuid

        for dt in DocType:
            doc = Document(
                contract_id=uuid.uuid4(),
                organization_id=uuid.uuid4(),
                doc_type=dt,
                amount=Decimal("100.00"),
            )
            assert doc.doc_type == dt
