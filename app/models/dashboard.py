from __future__ import annotations

from typing import Literal

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


class DashboardPanel(BaseModel):
    id: str
    title: str
    description: str
    visualization: Literal["metric", "status", "line", "bar", "table"]
    query: str
    unit: str | None = None
    thresholds: list[DashboardThreshold] = []
    layout: DashboardLayout
    validation: ValidationResult | None = None


class DashboardDefinition(BaseModel):
    version: int = 1
    title: str
    description: str
    default_time_range: str = "24h"
    refresh_interval_seconds: int = Field(default=300, ge=30, le=86400)
    scope: DashboardScope = DashboardScope()
    panels: list[DashboardPanel]


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
