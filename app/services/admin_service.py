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


def get_pending_properties() -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("properties")
        .select("id, titulo, tipo, zona, precio, moneda, created_at, profiles(full_name, publisher_type, email)")
        .eq("estado", "pending_review")
        .order("created_at", desc=False)
        .execute()
    )
    return {"data": result.data or []}


def approve_property(property_id: str, admin_id: str) -> dict:
    admin = get_supabase_admin()

    prop = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    if not prop.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if prop.data["estado"] != "pending_review":
        raise HTTPException(status_code=400, detail="La propiedad no está en revisión.")

    result = admin.table("properties").update({"estado": "published"}).eq("id", property_id).execute()
    updated = result.data[0]

    publisher = admin.table("profiles").select("email").eq("id", prop.data["publisher_id"]).maybe_single().execute()
    publisher_email = (publisher.data or {}).get("email", "")

    notify_publisher_property_approved(
        publisher_id=prop.data["publisher_id"],
        property_id=property_id,
        title=updated["titulo"],
        email=publisher_email,
    )

    _log_action(admin_id, "approve_property", "property", property_id)
    return updated


def reject_property(property_id: str, admin_id: str, reason: str) -> dict:
    admin = get_supabase_admin()

    prop = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    if not prop.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if prop.data["estado"] != "pending_review":
        raise HTTPException(status_code=400, detail="La propiedad no está en revisión.")

    result = admin.table("properties").update({
        "estado": "rejected",
        "rejection_reason": reason,
    }).eq("id", property_id).execute()
    updated = result.data[0]

    publisher = admin.table("profiles").select("email").eq("id", prop.data["publisher_id"]).maybe_single().execute()
    publisher_email = (publisher.data or {}).get("email", "")

    notify_publisher_property_rejected(
        publisher_id=prop.data["publisher_id"],
        property_id=property_id,
        title=updated["titulo"],
        email=publisher_email,
        reason=reason,
    )

    _log_action(admin_id, "reject_property", "property", property_id, {"reason": reason})
    return updated


def list_users(q: str = None, role: str = None, page: int = 1, page_size: int = 20) -> dict:
    admin = get_supabase_admin()
    query = admin.table("profiles").select("id, full_name, role, phone_verified, is_active, created_at, publisher_type", count="exact")

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

    from datetime import datetime, timezone
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
        .select("id, reason, description, resolved, created_at, properties(id, titulo), profiles(full_name)")
        .eq("resolved", False)
        .order("created_at", desc=False)
        .execute()
    )
    return {"data": result.data or []}


def resolve_report(report_id: str, admin_id: str, resolution_note: str = None) -> dict:
    admin = get_supabase_admin()

    from datetime import datetime, timezone
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