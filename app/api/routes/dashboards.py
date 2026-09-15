from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.config import settings
from app.core.management_access import require_management_access
from app.models.dashboard import (DashboardCloneRequest, DashboardDefinition, DashboardDesignRequest,
    DashboardRestoreRequest, DashboardSaveRequest, DashboardValidationResult, LogpressoTarget)
from app.services.dashboard_designer import DashboardDesigner, dashboard_to_yaml
from app.services.dashboard_operations import PRODUCT_TEMPLATES, analyze_dashboard, deployment_plan
from app.services.dashboard_store import DashboardStore


router = APIRouter()


def store():
    return DashboardStore(settings.dashboard_db_path)


@router.get("/templates")
def dashboard_templates():
    designer = DashboardDesigner()
    return {
        "items": designer.templates(),
        "examples": designer.example_requests(),
        "product_categories": PRODUCT_TEMPLATES,
    }


@router.get("")
def list_dashboards():
    return {"items": store().list()}


@router.post("", dependencies=[Depends(require_management_access)])
def save_dashboard(payload: DashboardSaveRequest):
    return store().save(payload.dashboard, change_note=payload.change_note)


@router.get("/{dashboard_id}")
def get_dashboard(dashboard_id: str, revision: int | None = Query(default=None, ge=1)):
    try:
        return store().get(dashboard_id, revision)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard not found") from error


@router.put("/{dashboard_id}", dependencies=[Depends(require_management_access)])
def update_dashboard(dashboard_id: str, payload: DashboardSaveRequest):
    try:
        store().get(dashboard_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard not found") from error
    return store().save(payload.dashboard, dashboard_id, payload.change_note)


@router.post("/{dashboard_id}/clone", dependencies=[Depends(require_management_access)])
def clone_dashboard(dashboard_id: str, payload: DashboardCloneRequest):
    try:
        return store().clone(dashboard_id, payload.title)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard not found") from error


@router.delete("/{dashboard_id}", status_code=204, dependencies=[Depends(require_management_access)])
def delete_dashboard(dashboard_id: str):
    try:
        store().delete(dashboard_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard not found") from error
    return Response(status_code=204)


@router.get("/{dashboard_id}/revisions")
def dashboard_revisions(dashboard_id: str):
    return {"items": store().revisions(dashboard_id)}


@router.get("/{dashboard_id}/diff")
def dashboard_diff(dashboard_id: str, old: int = Query(ge=1), new: int = Query(ge=1)):
    try:
        return {"content": store().diff(dashboard_id, old, new)}
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard revision not found") from error


@router.post("/{dashboard_id}/restore", dependencies=[Depends(require_management_access)])
def restore_dashboard(dashboard_id: str, payload: DashboardRestoreRequest):
    try:
        return store().restore(dashboard_id, payload.revision, payload.change_note)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="dashboard revision not found") from error


@router.post("/design", response_model=DashboardDefinition)
def design_dashboard(payload: DashboardDesignRequest):
    return DashboardDesigner().design(payload)


@router.post("/validate", response_model=DashboardValidationResult)
def validate_dashboard(payload: DashboardDefinition):
    _, result = DashboardDesigner().validate(payload)
    return result


@router.post("/analyze")
def analyze_dashboard_definition(payload: DashboardDefinition):
    return analyze_dashboard(payload)


@router.post("/deployment-plan")
def build_deployment_plan(payload: DashboardDefinition, base_url: str, verify_tls: bool = True):
    return deployment_plan(payload, LogpressoTarget(base_url=base_url, verify_tls=verify_tls))


@router.post("/export/json")
def export_dashboard_json(payload: DashboardDefinition):
    return {"filename": "logpresso-dashboard.json", "content": payload.model_dump_json(indent=2)}


@router.post("/export/yaml")
def export_dashboard_yaml(payload: DashboardDefinition):
    return {"filename": "logpresso-dashboard.yaml", "content": dashboard_to_yaml(payload)}
