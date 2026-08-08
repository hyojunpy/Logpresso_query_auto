from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.management_access import require_management_access
from app.models.response import OperationalMetricsResponse
from app.services.metrics_store import MetricsStore, metric_label

router = APIRouter()

@router.get("", dependencies=[Depends(require_management_access)])
def metrics_summary() -> OperationalMetricsResponse:
    store = MetricsStore(settings.metrics_db_path, settings.metrics_retention_days)
    metrics = store.summary()
    daily_items = store.daily_summary()
    return OperationalMetricsResponse(
        metrics=metrics,
        items=[
            {"metric": metric, "label": metric_label(metric), "count": count}
            for metric, count in metrics.items()
        ],
        daily_items=[
            {**item, "label": metric_label(str(item["metric"]))}
            for item in daily_items
        ],
        retention_days=settings.metrics_retention_days,
    )
