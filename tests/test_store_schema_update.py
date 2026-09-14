from io import BytesIO

from openpyxl import Workbook

from app.services.store_schema_knowledge import StoreSchemaKnowledge
from app.services.store_schema_update import StoreSchemaUpdate


def catalog_workbook() -> bytes:
    workbook = Workbook()
    workbook.active.title = "요약"
    workbook["요약"].append(["기준일", "2026-10-01"])
    for name in ("제품_목록", "스키마_목록", "필드_상세", "Raw_양식_공개", "공통_Syslog_필드"):
        workbook.create_sheet(name)
        workbook[name].append(["header"] * 10)
    workbook["제품_목록"].append(["Vendor", "Example WAF", "verified", "UDP", "514", "text", "public", "", "https://example.test"])
    workbook["스키마_목록"].append(["Vendor", "Example WAF", "Example Alert", "ALERT", "", "active", "https://example.test", "", "실제"])
    workbook["필드_상세"].append(["Vendor", "Example WAF", "Example Alert", "", "", "client_ip", "IP", "클라이언트 주소", "접속자 주소"])
    workbook["Raw_양식_공개"].append(["Example WAF", "ALERT", "UDP", "type|client_ip", "https://example.test"])
    workbook["공통_Syslog_필드"].append(["_time", "DATE", "발생 시간"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_xlsx_preview_compare_and_apply(tmp_path):
    updater = StoreSchemaUpdate(tmp_path / "store-schema.json")
    candidate = updater.parse_xlsx(catalog_workbook(), "catalog.xlsx")
    comparison = updater.compare(StoreSchemaKnowledge.bundled().payload, candidate)

    assert candidate["version"] == "2026-10-01"
    assert candidate["stats"] == {
        "products": 1, "schemas": 1, "schemas_with_fields": 1, "fields": 1, "raw_formats": 1,
    }
    assert "Example WAF" in comparison["products_added"]
    assert updater.save(candidate).exists()
    assert updater.current({})["source"] == "catalog.xlsx"
