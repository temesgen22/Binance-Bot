"""
Prometheus metrics endpoint for monitoring.
"""
from fastapi import APIRouter
from fastapi.responses import Response

from app.core.metrics import get_metrics, get_metrics_content_type

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint.
    
    Returns metrics in Prometheus text format for scraping.
    This endpoint is used by Prometheus to collect metrics.
    
    Returns:
        Response with Prometheus metrics in text format
    """
    metrics_data = get_metrics()
    return Response(
        content=metrics_data,
        media_type=get_metrics_content_type()
    )

