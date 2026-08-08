from app.models.request import Catalog, CatalogTable
from app.services.catalog_service import CatalogService


def test_save_creates_backup_and_restore_recovers_previous_catalog(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    first = Catalog(source="manual", tables=[CatalogTable(table_name="first")])
    second = Catalog(source="manual", tables=[CatalogTable(table_name="second")])
    service.save(first)
    service.save(second)
    backups = service.backups()
    assert len(backups) == 1
    restored = service.restore(backups[0]["name"])
    assert restored.tables[0].table_name == "first"


def test_restore_rejects_path_traversal(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    try:
        service.restore("../catalog.json")
    except ValueError as error:
        assert "invalid catalog backup name" in str(error)
    else:
        raise AssertionError("path traversal must be rejected")
