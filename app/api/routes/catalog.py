from fastapi import APIRouter, Body

from app.core.config import settings
from app.models.request import CatalogUpsertRequest
from app.services.catalog_service import CatalogService

router = APIRouter()


@router.get("")
def get_catalog():
    """TODO: require authentication before exposing operational catalog metadata."""
    catalog = CatalogService(settings.catalog_path).load()
    return catalog or {"tables": [], "source": "unknown"}


@router.put("")
def put_catalog(payload: CatalogUpsertRequest = Body(...)):
    """TODO: protect catalog administration with authentication/authorization."""
    return CatalogService(settings.catalog_path).save(payload.catalog)
