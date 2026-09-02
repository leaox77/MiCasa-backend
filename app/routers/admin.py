from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from app.dependencies import require_role
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["Admin"])

require_admin = require_role("admin")


class RejectRequest(BaseModel):
    reason: str


class SuspendRequest(BaseModel):
    reason: str


class ResolveReportRequest(BaseModel):
    resolution_note: Optional[str] = None


@router.get("/properties/pending")
def get_pending_properties(current_user: dict = Depends(require_admin)):
    return admin_service.get_pending_properties()


@router.post("/properties/{property_id}/approve")
def approve_property(property_id: str, current_user: dict = Depends(require_admin)):
    return admin_service.approve_property(property_id, current_user["id"])


@router.post("/properties/{property_id}/reject")
def reject_property(
    property_id: str,
    data: RejectRequest,
    current_user: dict = Depends(require_admin),
):
    if not data.reason.strip():
        raise HTTPException(status_code=400, detail="El motivo de rechazo es obligatorio.")
    return admin_service.reject_property(property_id, current_user["id"], data.reason)


@router.get("/users")
def list_users(
    q: Optional[str] = None,
    role: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(require_admin),
):
    return admin_service.list_users(q=q, role=role, page=page, page_size=page_size)


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    data: SuspendRequest,
    current_user: dict = Depends(require_admin),
):
    if current_user["id"] == user_id:
        raise HTTPException(status_code=400, detail="No podés suspender tu propia cuenta.")
    return admin_service.suspend_user(user_id, current_user["id"], data.reason)


@router.post("/users/{user_id}/reactivate")
def reactivate_user(user_id: str, current_user: dict = Depends(require_admin)):
    return admin_service.reactivate_user(user_id, current_user["id"])


@router.get("/reports")
def list_reports(current_user: dict = Depends(require_admin)):
    return admin_service.list_reports()


@router.post("/reports/{report_id}/resolve")
def resolve_report(
    report_id: str,
    data: ResolveReportRequest,
    current_user: dict = Depends(require_admin),
):
    return admin_service.resolve_report(report_id, current_user["id"], data.resolution_note)