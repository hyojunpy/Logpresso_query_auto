from app.models.request import Catalog, CatalogField, CatalogTable, RequestContext
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
    assert len(service.backups()) == 2


def test_restore_rejects_path_traversal(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    try:
        service.restore("../catalog.json")
    except ValueError as error:
        assert "invalid catalog backup name" in str(error)
    else:
        raise AssertionError("path traversal must be rejected")


def test_compare_backup_reports_table_and_field_changes(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    service.save(Catalog(source="manual", tables=[CatalogTable(table_name="firewall", fields=[CatalogField(field_name="src_ip")])]))
    service.save(Catalog(source="manual", tables=[CatalogTable(table_name="firewall", fields=[CatalogField(field_name="dst_ip")]), CatalogTable(table_name="insa")]))

    comparison = service.compare_backup(service.backups()[0]["name"])

    assert comparison["added_tables"] == ["insa"]
    assert comparison["changed_tables"] == [{"table_name": "firewall", "added_fields": ["dst_ip"], "removed_fields": ["src_ip"]}]


def test_schema_validation_exposes_rename_and_eval_field_lineage(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    service.save(Catalog(source="manual", tables=[CatalogTable(table_name="firewall", fields=[CatalogField(field_name="src_ip")])]))

    result = service.validate_query("table firewall\n| rename src_ip as allocated_ip\n| eval join_key = allocated_ip", RequestContext())

    lineage = {(item.output_field, item.operation) for item in result.field_lineage}
    assert ("src_ip", "source") in lineage
    assert ("allocated_ip", "rename") in lineage
    assert ("join_key", "eval") in lineage


def test_field_lineage_identifies_right_join_field_without_guessing_ambiguous_fields(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    service.save(Catalog(source="manual", tables=[
        CatalogTable(table_name="firewall", fields=[CatalogField(field_name="src_ip"), CatalogField(field_name="ip")]),
        CatalogTable(table_name="insa", fields=[CatalogField(field_name="employee_ip"), CatalogField(field_name="ip")]),
    ]))

    result = service.validate_query(
        "table firewall\n| rename src_ip as source_ip\n| join type=left _join_key [\n table insa\n | rename employee_ip as employee_address\n]\n| eval common_ip = ip",
        RequestContext(),
    )

    lineage = {item.output_field: item for item in result.field_lineage}
    assert lineage["source_ip"].source_table == "firewall"
    assert lineage["employee_address"].source_table == "insa"
    assert lineage["common_ip"].source_table is None


def test_join_output_collision_warns_and_fields_marks_lineage_excluded(tmp_path):
    service = CatalogService(tmp_path / "catalog.json")
    service.save(Catalog(source="manual", tables=[
        CatalogTable(table_name="firewall", fields=[CatalogField(field_name="ip"), CatalogField(field_name="action")]),
        CatalogTable(table_name="insa", fields=[CatalogField(field_name="ip"), CatalogField(field_name="employee_id")]),
    ]))

    result = service.validate_query("table firewall\n| join type=left _join_key [ table insa ]\n| fields action, employee_id", RequestContext())

    assert "join_output_field_collision" in {item.code for item in result.warnings}
    assert all(item.status == "excluded" for item in result.field_lineage if item.output_field == "ip")
