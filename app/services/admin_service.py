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
    """TODO / IMPORTANTE (pendiente coherencia de schema con Leandro): esta
    función dependía por completo de la columna "status" (filtraba
    'pending_review'). Sin esa columna no hay forma de saber qué propiedades
    están pendientes de revisión — se deshabilita en vez de devolver una
    lista que no representa lo que dice representar (p. ej. todas o
    ninguna)."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Listado de pendientes no disponible: falta la columna 'status' en el schema real (pendiente de definir con Leandro).",
    )


def approve_property(property_id: str, admin_id: str) -> dict:
    """TODO (pendiente coherencia de schema con Leandro): dependía de leer
    y escribir "estado". Deshabilitada por el mismo motivo que
    get_pending_properties."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Aprobar propiedad no disponible: falta la columna 'status' en el schema real (pendiente de definir con Leandro).",
    )


def reject_property(property_id: str, admin_id: str, reason: str) -> dict:
    """TODO (pendiente coherencia de schema con Leandro): mismo motivo que
    approve_property. `rejection_reason` sí existe como columna real, pero
    no tiene sentido setearla sin poder validar/mover el estado."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Rechazar propiedad no disponible: falta la columna 'status' en el schema real (pendiente de definir con Leandro).",
    )


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
        .select("id, reason, description, resolved, created_at, properties(id, title), profiles(full_name)")
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