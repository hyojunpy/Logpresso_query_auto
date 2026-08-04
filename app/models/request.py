from typing import Literal

from pydantic import BaseModel, Field


MAX_NATURAL_LANGUAGE_LENGTH = 4_000
MAX_QUERY_LENGTH = 20_000
MAX_KNOWN_TABLES = 200
MAX_KNOWN_FIELDS = 500


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


class QueryIntent(BaseModel):
    objective: str
    query_type: Literal["adhoc", "realtime", "stream", "scheduled", "unknown"] = "unknown"
    source_type: Literal["table", "logger", "stream", "fulltext", "file", "unknown"] = "unknown"
    tables: list[str] = []
    loggers: list[str] = []
    streams: list[str] = []
    stream_window: str | None = None
    logger_window: str | None = None
    file_command: str | None = None
    file_path: str | None = None
    archive_member: str | None = None
    fulltext_expression: str | None = None
    time_range: TimeRange | None = None
    source_order: Literal["asc", "desc"] | None = None
    use_parameterized_time_range: bool = False
    filters: list[FilterCondition] = []
    post_filters: list[FilterCondition] = []
    selected_fields: list[str] = []
    computed_fields: list[ComputedField] = []
    parser_name: str | None = None
    structured_parser: Literal["parsejson", "parsecsv"] | None = None
    structured_parser_field: str | None = None
    parser_flatten: bool = False
    parser_tab: bool = False
    explode_fields: list[str] = []
    renames: list[RenameOperation] = []
    group_by: list[str] = []
    aggregations: list[Aggregation] = []
    aggregation_command: Literal["stats", "rollup"] = "stats"
    final_aggregations: list[Aggregation] = []
    sort: list[SortCondition] = []
    offset: int | None = None
    limit: int | None = None
    output_format: str | None = None
    assumptions: list[str] = []
    missing_information: list[str] = []


class RequestContext(BaseModel):
    product: str | None = Field(default=None, max_length=32)
    version: str | None = Field(default=None, max_length=64)
    known_tables: list[str] = Field(default_factory=list, max_length=MAX_KNOWN_TABLES)
    known_fields: list[str] = Field(default_factory=list, max_length=MAX_KNOWN_FIELDS)


class GenerateQueryRequest(BaseModel):
    request: str = Field(
        min_length=1,
        max_length=MAX_NATURAL_LANGUAGE_LENGTH,
        examples=["최근 24시간 동안 firewall_logs에서 출발지 IP별 차단 건수를 집계해서 많은 순으로 20개 보여줘"],
    )
    context: RequestContext = Field(default_factory=RequestContext)


class ValidateQueryRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=MAX_QUERY_LENGTH,
        examples=["table duration=24h firewall_logs\n| stats count by src_ip"],
    )
