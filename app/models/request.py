from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TimeRange(BaseModel):
    mode: Literal["duration", "absolute", "unknown"] = "unknown"
    duration: str | None = None
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None


class FilterCondition(BaseModel):
    field: str
    operator: str = "=="
    value: str
    value_type: str = "string"
    conjunction: Literal["and", "or"] = "and"


class ComputedField(BaseModel):
    name: str
    expression: str


class Aggregation(BaseModel):
    function: str
    field: str | None = None
    alias: str | None = None


class SortCondition(BaseModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class RenameOperation(BaseModel):
    field: str
    new_name: str


class JoinSpec(BaseModel):
    command: Literal["join", "streamjoin"] = "join"
    join_type: Literal["inner", "left", "right", "full", "leftonly", "rightonly"] = "inner"
    left_source_type: Literal["table", "stream", "logger"] = "table"
    left_table: str
    right_table: str
    left_key: str
    right_key: str
    left_rename: str | None = None
    right_rename: str | None = None
    helper_key: str = "_join_key"
    left_filters: list[FilterCondition] = []
    right_filters: list[FilterCondition] = []


class QueryIntent(BaseModel):
    objective: str
    query_type: Literal["adhoc", "realtime", "stream", "scheduled", "unknown"] = "unknown"
    source_type: Literal["table", "logger", "stream", "fulltext", "file", "unknown"] = "unknown"
    tables: list[str] = []
    table_candidates: list[str] = []
    loggers: list[str] = []
    streams: list[str] = []
    forward_streams: list[str] = []
    fulltext_expression: str | None = None
    time_range: TimeRange | None = None
    use_parameterized_time_range: bool = False
    filters: list[FilterCondition] = []
    post_filters: list[FilterCondition] = []
    selected_fields: list[str] = []
    computed_fields: list[ComputedField] = []
    renames: list[RenameOperation] = []
    join: JoinSpec | None = None
    group_by: list[str] = []
    aggregations: list[Aggregation] = []
    aggregation_command: Literal["stats", "rollup"] = "stats"
    final_aggregations: list[Aggregation] = []
    sort: list[SortCondition] = []
    limit: int | None = None
    output_format: str | None = None
    assumptions: list[str] = []
    missing_information: list[str] = []


class CatalogField(BaseModel):
    field_name: str
    field_type: str = "unknown"
    description: str | None = None
    nullable: bool | None = None


class CatalogTable(BaseModel):
    table_name: str
    node: str | None = None
    namespace: str | None = None
    description: str | None = None
    fields: list[CatalogField] = []


class CatalogFunctionTypeRule(BaseModel):
    function_name: str
    argument_index: int = 0
    allowed_field_types: list[str]
    description: str | None = None


class Catalog(BaseModel):
    tables: list[CatalogTable] = []
    catalog_version: str | None = None
    updated_at: str | None = None
    source: Literal["manual", "fixture", "external_sync", "unknown"] = "unknown"
    function_type_rules: list[CatalogFunctionTypeRule] = []


class RequestContext(BaseModel):
    product: str | None = None
    version: str | None = None
    known_tables: list[str] = []
    known_fields: list[str] = []
    known_loggers: list[str] = []
    known_streams: list[str] = []
    catalog: Catalog | None = None
    request_catalog: Catalog | None = None


class GenerateQueryRequest(BaseModel):
    request: str = Field(min_length=1)
    context: RequestContext = RequestContext()


class ValidateQueryRequest(BaseModel):
    query: str = Field(min_length=1, examples=["table duration=24h firewall_logs\n| stats count by src_ip"])
    catalog: Catalog | None = None
    context: RequestContext = RequestContext()


class CatalogUpsertRequest(BaseModel):
    catalog: Catalog


class FeedbackRequest(BaseModel):
    request_text: str = Field(min_length=1)
    generated_query: str | None = None
    result_status: str
    rating: Literal["positive", "negative", "neutral"]
    feedback_comment: str | None = None
    issue_type: Literal["wrong_table", "wrong_field", "wrong_time_range", "invalid_syntax", "unsafe_query", "irrelevant_query", "other"] | None = None
    store_raw_text: bool = False
