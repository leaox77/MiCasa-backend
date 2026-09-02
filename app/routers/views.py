from fastapi import APIRouter, Depends, Request
from app.dependencies import get_current_user_optional
from app.services import views_service

router = APIRouter(prefix="/properties", tags=["Views"])


@router.post("/{property_id}/view", status_code=204)
def register_view(
    property_id: str,
    request: Request,
    current_user: dict | None = Depends(get_current_user_optional),
):
    session_id = request.headers.get("X-Session-ID")
    views_service.register_view(
        property_id=property_id,
        user_id=current_user["id"] if current_user else None,
        session_id=session_id if not current_user else None,
    )