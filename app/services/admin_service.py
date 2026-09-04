from datetime import datetime, timezone

from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from app.services.notification_service import (
    notify_publisher_property_approved,
    notify_publisher_property_rejected,
)


def _log_action(admin_id: str, action: str, target_type: str, target_id: str, details: dict = None):
    admin = get_supabase_admin()
    admin.table("admin_audit_log").insert({
        "admin_id": admin_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details or {},
    }).execute()


def _get_user_email(user_id: str) -> str:
    """El email vive en Supabase Auth (auth.users), no en public.profiles
    — profiles NO tiene columna "email" en la BD real (Bug 1 del audit).
    Se resuelve acá vía la API admin de Auth, no con un select a profiles.
    Verificado contra supabase-py==2.4.6: admin.auth.admin.get_user_by_id
    existe y devuelve un UserResponse con .user.email."""
    admin = get_supabase_admin()
    try:
        response = admin.auth.admin.get_user_by_id(user_id)
        return response.user.email or ""
    except Exception:
        return ""


def get_pending_properties() -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("properties")
        .select("id, title, price, currency, property_type, zone, city, publisher_id, created_at")
        .eq("status", "pending_review")
        .order("created_at", desc=False)
        .execute()
    )
    return {"data": result.data or []}


def approve_property(property_id: str, admin_id: str) -> dict:
    admin = get_supabase_admin()

    existing = (
        admin.table("properties")
        .select("id, title, publisher_id, status")
        .eq("id", property_id)
        .maybe_single()
        .execute()
    )
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if property_row["status"] != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden aprobar propiedades en 'pending_review' (esta está en '{property_row['status']}').",
        )

    result = admin.table("properties").update({
        "status": "published",
        "reviewed_by": admin_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": None,
    }).eq("id", property_id).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo aprobar la propiedad.")

    updated_row = result.data[0]

    notify_publisher_property_approved(
        publisher_id=property_row["publisher_id"],
        property_id=property_id,
        title=property_row["title"],
        email=_get_user_email(property_row["publisher_id"]),
    )

    _log_action(admin_id, "approve_property", "property", property_id)
    return updated_row


def reject_property(property_id: str, admin_id: str, reason: str) -> dict:
    admin = get_supabase_admin()

    existing = (
        admin.table("properties")
        .select("id, title, publisher_id, status")
        .eq("id", property_id)
        .maybe_single()
        .execute()
    )
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if property_row["status"] != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden rechazar propiedades en 'pending_review' (esta está en '{property_row['status']}').",
        )

    result = admin.table("properties").update({
        "status": "rejected",
        "reviewed_by": admin_id,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "rejection_reason": reason,
    }).eq("id", property_id).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo rechazar la propiedad.")

    updated_row = result.data[0]

    notify_publisher_property_rejected(
        publisher_id=property_row["publisher_id"],
        property_id=property_id,
        title=property_row["title"],
        email=_get_user_email(property_row["publisher_id"]),
        reason=reason,
    )

    _log_action(admin_id, "reject_property", "property", property_id, {"reason": reason})
    return updated_row


def list_users(q: str = None, role: str = None, page: int = 1, page_size: int = 20) -> dict:
    admin = get_supabase_admin()
    query = admin.table("profiles").select(
        "id, full_name, role, phone_verified, is_active, created_at, publisher_type", count="exact"
    )

    if role:
        query = query.eq("role", role)

    start = (page - 1) * page_size
    query = query.range(start, start + page_size - 1)

    result = query.execute()
    return {"data": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}


def suspend_user(user_id: str, admin_id: str, reason: str) -> dict:
    admin = get_supabase_admin()

    target = admin.table("profiles").select("id, role").eq("id", user_id).maybe_single().execute()
    if not target.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    if target.data["role"] == "admin":
        raise HTTPException(status_code=400, detail="No se puede suspender a un administrador.")

    result = admin.table("profiles").update({
        "is_active": False,
        "suspended_at": datetime.now(timezone.utc).isoformat(),
        "suspended_reason": reason,
    }).eq("id", user_id).execute()

    _log_action(admin_id, "suspend_user", "user", user_id, {"reason": reason})
    return result.data[0]


def reactivate_user(user_id: str, admin_id: str) -> dict:
    admin = get_supabase_admin()

    target = admin.table("profiles").select("id").eq("id", user_id).maybe_single().execute()
    if not target.data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    result = admin.table("profiles").update({
        "is_active": True,
        "suspended_at": None,
        "suspended_reason": None,
    }).eq("id", user_id).execute()

    _log_action(admin_id, "reactivate_user", "user", user_id)
    return result.data[0]


def list_reports() -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("reports")
        .select("id, reason, description, resolved, created_at, properties(id, title), profiles(full_name)")
        .eq("resolved", False)
        .order("created_at", desc=False)
        .execute()
    )
    return {"data": result.data or []}


def resolve_report(report_id: str, admin_id: str, resolution_note: str = None) -> dict:
    admin = get_supabase_admin()

    result = admin.table("reports").update({
        "resolved": True,
        "resolved_by": admin_id,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "resolution_note": resolution_note,
    }).eq("id", report_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Denuncia no encontrada.")

    _log_action(admin_id, "resolve_report", "report", report_id)
    return result.data[0]