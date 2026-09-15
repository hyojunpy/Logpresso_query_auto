from fastapi import APIRouter

from app.models.dashboard import DashboardDefinition, DashboardDesignRequest, DashboardValidationResult
from app.services.dashboard_designer import DashboardDesigner, dashboard_to_yaml


router = APIRouter()


@router.get("/templates")
def dashboard_templates():
    return {"items": DashboardDesigner().templates()}


@router.post("/design", response_model=DashboardDefinition)
def design_dashboard(payload: DashboardDesignRequest):
    return DashboardDesigner().design(payload)


@router.post("/validate", response_model=DashboardValidationResult)
def validate_dashboard(payload: DashboardDefinition):
    _, result = DashboardDesigner().validate(payload)
    return result


@router.post("/export/json")
def export_dashboard_json(payload: DashboardDefinition):
    return {"filename": "logpresso-dashboard.json", "content": payload.model_dump_json(indent=2)}


@router.post("/export/yaml")
def export_dashboard_yaml(payload: DashboardDefinition):
    return {"filename": "logpresso-dashboard.yaml", "content": dashboard_to_yaml(payload)}
