from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.services import notification_service as notifications_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(current_user: dict = Depends(get_current_user)):
    return notifications_service.list_notifications(current_user["id"])


@router.patch("/read-all")
def mark_all_as_read(current_user: dict = Depends(get_current_user)):
    return notifications_service.mark_all_as_read(current_user["id"])


@router.patch("/{notification_id}/read")
def mark_as_read(notification_id: str, current_user: dict = Depends(get_current_user)):
    return notifications_service.mark_as_read(notification_id, current_user["id"])