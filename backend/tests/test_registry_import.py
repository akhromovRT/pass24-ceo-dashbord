from sqlmodel import Session, select

from app.models import Alert, ClientObject, Organization, OrgStatus
from app.parser.registry import (
    ParsedRegistryCompany,
    ParsedRegistryObject,
    RegistryParseResult,
)
from app.services.import_service import ImportService


def _make_company(inn, name, objects=None, **kw):
    return ParsedRegistryCompany(
        inn=inn,
        company_name=name,
        objects=objects or [],
        **kw,
    )


def _make_object(name, **kw):
    return ParsedRegistryObject(name=name, **kw)


def _result(companies, skipped=None, total=None):
    return RegistryParseResult(
        filename="test.xlsx",
        companies=companies,
        skipped_no_inn=skipped or [],
        total_rows=total if total is not None else sum(max(1, len(c.objects)) for c in companies),
    )


class TestRegistryImport:
    def test_marks_existing_org_in_registry(self, db_session: Session):
        org = Organization(inn="7703746155", name_1c="ОНВИ Сервис", in_registry=False)
        db_session.add(org)
        db_session.commit()

        result = _result(
            [
                _make_company(
                    "7703746155",
                    "ОНВИ Сервис",
                    objects=[_make_object("Офис", cloud_url="https://onvi.pass24online.ru")],
                )
            ]
        )

        run = ImportService(db_session).process_registry_import(result, file_hash="abc")
        db_session.refresh(org)

        assert org.in_registry is True
        assert run.delta_summary["orgs_marked_in_registry"] == 1
        assert run.delta_summary["orgs_created"] == 0
        assert run.delta_summary["objects_added"] == 1

    def test_creates_new_org_as_prospect(self, db_session: Session):
        result = _result(
            [_make_company("1234567890", "Новая Компания ООО", objects=[_make_object("Объект 1")])]
        )
        run = ImportService(db_session).process_registry_import(result, file_hash="abc")
        org = db_session.exec(select(Organization).where(Organization.inn == "1234567890")).first()
        assert org is not None
        assert org.in_registry is True
        assert org.status == OrgStatus.PROSPECT
        assert run.new_buyers == 1

    def test_transfers_contract_and_active_doc(self, db_session: Session):
        result = _result(
            [
                _make_company(
                    "1234567890",
                    "Test",
                    contract_1c="Договор № 1 от 01.01.2024",
                    active_doc="ДС № 2 от 01.06.2025",
                    objects_count_declared=3,
                    objects=[_make_object("X")],
                )
            ]
        )
        ImportService(db_session).process_registry_import(result, file_hash="abc")
        org = db_session.exec(select(Organization).where(Organization.inn == "1234567890")).first()
        assert org.contract_1c_raw == "Договор № 1 от 01.01.2024"
        assert org.active_doc_raw == "ДС № 2 от 01.06.2025"
        assert org.objects_count_declared == 3

    def test_multiple_objects_for_same_company(self, db_session: Session):
        result = _result(
            [
                _make_company(
                    "1234567890",
                    "ПИК-КОМФОРТ",
                    objects=[
                        _make_object(
                            "ЖК Вавилова 4", cloud_url="https://vavilova4.pass24online.ru"
                        ),
                        _make_object(
                            "ЖК Вандер Парк", cloud_url="https://vanderpark.pass24online.ru"
                        ),
                    ],
                )
            ]
        )
        ImportService(db_session).process_registry_import(result, file_hash="abc")
        org = db_session.exec(select(Organization).where(Organization.inn == "1234567890")).first()
        objects = db_session.exec(
            select(ClientObject).where(ClientObject.organization_id == org.id)
        ).all()
        assert len(objects) == 2
        names = {o.name for o in objects}
        assert names == {"ЖК Вавилова 4", "ЖК Вандер Парк"}

    def test_idempotent_object_upsert(self, db_session: Session):
        # First import
        result = _result(
            [
                _make_company(
                    "1234567890", "X", objects=[_make_object("Obj1", cloud_url="https://a.com")]
                )
            ]
        )
        ImportService(db_session).process_registry_import(result, file_hash="hash1")

        # Second import: same name, different cloud_url → should update, not add
        result2 = _result(
            [
                _make_company(
                    "1234567890", "X", objects=[_make_object("Obj1", cloud_url="https://b.com")]
                )
            ]
        )
        run = ImportService(db_session).process_registry_import(result2, file_hash="hash2")

        objects = db_session.exec(select(ClientObject)).all()
        assert len(objects) == 1
        assert objects[0].cloud_url == "https://b.com"
        assert run.delta_summary["objects_updated"] == 1

    def test_existing_org_fields_filled_only_when_empty(self, db_session: Session):
        # Org already has cloud_url — registry should NOT overwrite
        org = Organization(inn="7703746155", name_1c="X", cloud_url="https://old.com")
        db_session.add(org)
        db_session.commit()

        result = _result(
            [
                _make_company(
                    "7703746155", "X", objects=[_make_object("Y", cloud_url="https://new.com")]
                )
            ]
        )
        ImportService(db_session).process_registry_import(result, file_hash="abc")
        db_session.refresh(org)
        assert org.cloud_url == "https://old.com"  # not overwritten

    def test_company_without_objects_still_marked(self, db_session: Session):
        # Section company without an object name (e.g. "Расторгнутые → УК РЕСПЕКТ")
        result = _result([_make_company("7718980736", "УК РЕСПЕКТ СЕРВИС")])
        run = ImportService(db_session).process_registry_import(result, file_hash="abc")
        org = db_session.exec(select(Organization).where(Organization.inn == "7718980736")).first()
        assert org.in_registry is True
        assert run.delta_summary["objects_added"] == 0

    def test_creates_alert_for_new_org(self, db_session: Session):
        result = _result([_make_company("1234567890", "Foo", objects=[_make_object("X")])])
        ImportService(db_session).process_registry_import(result, file_hash="abc")
        alerts = db_session.exec(select(Alert)).all()
        assert len(alerts) == 1
        assert "реестра" in alerts[0].title

    def test_skipped_no_inn_recorded_in_errors(self, db_session: Session):
        result = _result(
            companies=[_make_company("1234567890", "OK", objects=[_make_object("X")])],
            skipped=[
                {"row": 5, "company": "Расторгнутые клиенты"},
                {"row": 10, "company": "Лицензии"},
            ],
            total=3,
        )
        run = ImportService(db_session).process_registry_import(result, file_hash="abc")
        assert run.delta_summary["skipped_no_inn"] == 2
        assert run.errors == [
            {"row": 5, "company": "Расторгнутые клиенты"},
            {"row": 10, "company": "Лицензии"},
        ]
