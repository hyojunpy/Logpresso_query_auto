from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.request import RequestContext
from app.models.response import ValidationResult


class DashboardScope(BaseModel):
    manufacturer: str | None = None
    product: str | None = None
    schema_name: str | None = None


class DashboardLayout(BaseModel):
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    width: int = Field(ge=1, le=12)
    height: int = Field(ge=1, le=12)


class DashboardThreshold(BaseModel):
    operator: Literal["<", "<=", "==", ">=", ">"]
    value: float
    severity: Literal["info", "warning", "critical"]
    label: str


class DashboardVariable(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    label: str
    kind: Literal["text", "select", "time_range"] = "text"
    default: str | None = None
    options: list[str] = []
    required: bool = False


class DashboardPanel(BaseModel):
    id: str
    title: str
    description: str
    visualization: Literal["metric", "status", "line", "bar", "table"]
    query: str
    unit: str | None = None
    thresholds: list[DashboardThreshold] = Field(default_factory=list)
    layout: DashboardLayout
    validation: ValidationResult | None = None


class DashboardDefinition(BaseModel):
    version: int = 1
    title: str
    description: str
    default_time_range: str = "24h"
    refresh_interval_seconds: int = Field(default=300, ge=30, le=86400)
    scope: DashboardScope = Field(default_factory=DashboardScope)
    variables: list[DashboardVariable] = Field(default_factory=list)
    panels: list[DashboardPanel]


class DashboardRecord(BaseModel):
    id: str
    revision: int
    dashboard: DashboardDefinition
    created_at: datetime
    updated_at: datetime


class DashboardSummary(BaseModel):
    id: str
    revision: int
    title: str
    scope: DashboardScope
    panel_count: int
    updated_at: datetime


class DashboardSaveRequest(BaseModel):
    dashboard: DashboardDefinition
    change_note: str = Field(default="", max_length=500)


class DashboardCloneRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class DashboardRestoreRequest(BaseModel):
    revision: int = Field(ge=1)
    change_note: str = Field(default="revision restore", max_length=500)


class DashboardAnalysis(BaseModel):
    score: int = Field(ge=0, le=100)
    estimated_query_weight: int = Field(ge=0)
    warnings: list[str]
    recommendations: list[str]
    panel_details: list[dict[str, Any]]


class LogpressoTarget(BaseModel):
    base_url: str = Field(pattern=r"^https?://")
    verify_tls: bool = True
    product: str = "Logpresso Sonar"


class DashboardDeploymentPlan(BaseModel):
    target: LogpressoTarget
    compatible: bool
    dashboard_title: str
    variable_count: int
    widget_count: int
    steps: list[str]
    warnings: list[str]
    payload: dict[str, Any]


class DashboardDesignRequest(BaseModel):
    request: str = Field(min_length=1, max_length=4000)
    manufacturer: str | None = None
    store_product: str | None = None
    store_schema: str | None = None
    table_name: str | None = None
    default_time_range: str = "24h"
    refresh_interval_seconds: int = Field(default=300, ge=30, le=86400)
    context: RequestContext = RequestContext()


class DashboardValidationResult(BaseModel):
    valid: bool
    panel_count: int
    valid_panels: int
    invalid_panels: int
    panels: list[dict]
