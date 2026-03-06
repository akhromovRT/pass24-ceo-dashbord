from decimal import Decimal

from app.models.organization import OrgStatus, OrgType, Organization
from app.models.contract import Contract, ContractStatus, ContractType
from app.models.document import DocType, Document
from app.models.snapshot import MonthlySnapshot
from app.models.import_run import ImportRun, ImportStatus
from app.models.user import User, UserRole
from app.models.alert import Alert, AlertType, AlertSeverity, AlertStatus


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


class TestMonthlySnapshot:
    def test_create_snapshot(self):
        import uuid

        org_id = uuid.uuid4()
        snap = MonthlySnapshot(
            organization_id=org_id,
            year=2026,
            month=1,
            debt_start=Decimal("10000.00"),
            sold=Decimal("5000.00"),
            paid=Decimal("3000.00"),
            debt_end=Decimal("12000.00"),
            collectability=Decimal("60.00"),
            is_active=True,
        )
        assert snap.organization_id == org_id
        assert snap.year == 2026
        assert snap.month == 1
        assert snap.debt_start == Decimal("10000.00")
        assert snap.sold == Decimal("5000.00")
        assert snap.paid == Decimal("3000.00")
        assert snap.debt_end == Decimal("12000.00")
        assert snap.collectability == Decimal("60.00")
        assert snap.is_active is True

    def test_default_is_active(self):
        import uuid

        snap = MonthlySnapshot(
            organization_id=uuid.uuid4(), year=2026, month=2,
        )
        assert snap.is_active is True


class TestImportRun:
    def test_create_import_run(self):
        run = ImportRun(
            filename="debt_report.xlsx",
            file_hash="abc123" * 10 + "abcd",
            status=ImportStatus.COMPLETED,
            buyers_count=243,
            contracts_count=200,
            documents_count=1000,
        )
        assert run.filename == "debt_report.xlsx"
        assert run.status == ImportStatus.COMPLETED
        assert run.buyers_count == 243

    def test_default_status_is_pending(self):
        run = ImportRun(filename="test.xlsx", file_hash="a" * 64)
        assert run.status == ImportStatus.PENDING

    def test_json_fields(self):
        run = ImportRun(
            filename="test.xlsx",
            file_hash="a" * 64,
            errors=["row 5: missing INN"],
            delta_summary={"new_buyers": 3},
        )
        assert run.errors == ["row 5: missing INN"]
        assert run.delta_summary == {"new_buyers": 3}


class TestUser:
    def test_create_user(self):
        user = User(
            name="Алексей Хромов",
            email="admin@onvi-service.ru",
            hashed_password="hashed",
            role=UserRole.ADMIN,
        )
        assert user.name == "Алексей Хромов"
        assert user.email == "admin@onvi-service.ru"
        assert user.role == UserRole.ADMIN
        assert user.is_active is True

    def test_default_role_is_viewer(self):
        user = User(
            name="Test", email="test@test.ru", hashed_password="hashed",
        )
        assert user.role == UserRole.VIEWER

    def test_all_roles(self):
        for role in UserRole:
            user = User(
                name="T", email=f"{role.value}@t.ru", hashed_password="h", role=role,
            )
            assert user.role == role


class TestAlert:
    def test_create_alert(self):
        import uuid

        org_id = uuid.uuid4()
        alert = Alert(
            organization_id=org_id,
            alert_type=AlertType.NON_PAYMENT,
            severity=AlertSeverity.CRITICAL,
            title="Неоплата 3+ месяцев",
            description="Клиент не платит с октября",
            metric_value=90.0,
            threshold=60.0,
        )
        assert alert.organization_id == org_id
        assert alert.alert_type == AlertType.NON_PAYMENT
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.title == "Неоплата 3+ месяцев"
        assert alert.status == AlertStatus.OPEN

    def test_default_status_is_open(self):
        alert = Alert(
            alert_type=AlertType.NEW_CLIENT,
            severity=AlertSeverity.INFO,
            title="Новый клиент",
        )
        assert alert.status == AlertStatus.OPEN

    def test_all_alert_types(self):
        for at in AlertType:
            alert = Alert(alert_type=at, title="test", severity=AlertSeverity.INFO)
            assert alert.alert_type == at
