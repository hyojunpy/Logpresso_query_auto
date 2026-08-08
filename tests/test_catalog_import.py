import pytest

from app.services.catalog_import import CatalogImportError, catalog_from_csv_bytes


def test_parses_csv_catalog_with_required_columns():
    catalog = catalog_from_csv_bytes(
        b"table_name,field_name,field_type,description\nfirewall,src_ip,ip,source\n"
    )
    assert catalog.tables[0].table_name == "firewall"
    assert catalog.tables[0].fields[0].field_type == "ip"


def test_rejects_missing_csv_header():
    with pytest.raises(CatalogImportError, match="Missing required CSV columns"):
        catalog_from_csv_bytes(b"table_name,field_name\nfirewall,src_ip\n")


def test_rejects_duplicate_field_with_row_number():
    with pytest.raises(CatalogImportError, match="row 3"):
        catalog_from_csv_bytes(
            b"table_name,field_name,field_type,description\nfirewall,src_ip,ip,one\nfirewall,src_ip,ip,two\n"
        )


def test_rejects_empty_field_with_row_number():
    with pytest.raises(CatalogImportError, match="field_name is required \\(row 2\\)"):
        catalog_from_csv_bytes(
            b"table_name,field_name,field_type,description\nfirewall,,ip,missing field\n"
        )


def test_parses_optional_table_metadata_and_nullable_column():
    catalog = catalog_from_csv_bytes(
        b"table_name,field_name,field_type,description,node,namespace,table_description,nullable\n"
        b"firewall,src_ip,ip,source,node-a,security,Firewall events,false\n"
    )
    table = catalog.tables[0]
    assert (table.node, table.namespace, table.description) == ("node-a", "security", "Firewall events")
    assert table.fields[0].nullable is False


def test_rejects_invalid_nullable_value():
    with pytest.raises(CatalogImportError, match="nullable must be true or false"):
        catalog_from_csv_bytes(
            b"table_name,field_name,field_type,description,nullable\nfirewall,src_ip,ip,source,maybe\n"
        )
