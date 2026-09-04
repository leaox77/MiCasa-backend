from fastapi import APIRouter, Depends, Query
from app.dependencies import require_verified_publisher
from app.schemas.properties import PropertyStatus
from app.services import publisher_service

router = APIRouter(prefix="/publisher", tags=["Publisher"])


@router.get("/properties")
def my_properties(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    status: PropertyStatus | None = Query(None, description="Filtrar por status."),
    current_user: dict = Depends(require_verified_publisher),
):
    return publisher_service.get_my_properties(
        current_user["id"], page, page_size, prop_status=status.value if status else None
    )


@router.get("/metrics")
def my_metrics(current_user: dict = Depends(require_verified_publisher)):
    return publisher_service.get_my_metrics(current_user["id"])


@router.post("/properties/{property_id}/renew")
def renew_property(property_id: str, current_user: dict = Depends(require_verified_publisher)):
    return publisher_service.renew_property(property_id, current_user["id"])