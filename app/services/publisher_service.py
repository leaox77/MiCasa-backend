from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from app.schemas.properties import PropertyStatus

RENEWAL_DAYS = 60
EXPIRING_SOON_DAYS = 7  # umbral para "expiring_soon" — ajustable si querés otro número


def get_my_properties(
    publisher_id: str, page: int = 1, page_size: int = 20, prop_status: str | None = None
) -> dict:
    """Listado de propiedades del publisher logueado, con status real."""
    admin = get_supabase_admin()
    query = (
        admin.table("properties")
        .select(
            "id, title, zone, price, currency, property_type, status, created_at, "
            "updated_at, expires_at, view_count, interest_count",
            count="exact",
        )
        .eq("publisher_id", publisher_id)
    )
    if prop_status is not None:
        query = query.eq("status", prop_status)

    start = (page - 1) * page_size
    query = query.order("created_at", desc=True).range(start, start + page_size - 1)
    result = query.execute()
    return {"data": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}


def get_my_metrics(publisher_id: str) -> dict:
    """Métricas del dashboard del publisher, con status real."""
    admin = get_supabase_admin()

    rows = (
        admin.table("properties")
        .select("id, status, view_count, interest_count, expires_at")
        .eq("publisher_id", publisher_id)
        .execute()
    ).data or []

    total_views = sum(r.get("view_count", 0) or 0 for r in rows)
    total_interests = sum(r.get("interest_count", 0) or 0 for r in rows)
    total_published = sum(1 for r in rows if r.get("status") == PropertyStatus.published.value)
    active_properties = sum(
        1 for r in rows if r.get("status") in (PropertyStatus.published.value, PropertyStatus.paused.value)
    )

    threshold = datetime.now(timezone.utc) + timedelta(days=EXPIRING_SOON_DAYS)
    expiring_soon = sum(
        1
        for r in rows
        if r.get("status") == PropertyStatus.published.value
        and r.get("expires_at") is not None
        and datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00")) <= threshold
    )

    return {
        "total_published": total_published,
        "total_views": total_views,
        "total_interests": total_interests,
        "active_properties": active_properties,
        "expiring_soon": expiring_soon,
    }


def renew_property(property_id: str, publisher_id: str) -> dict:
    """Válido desde 'published' (extiende expires_at) o 'expired' (la
    vuelve a publicar). El trigger trg_property_published solo dispara en
    la transición expired->published (recalcula published_at/expires_at);
    para el caso 'ya published' seteamos expires_at a mano porque el
    trigger no se activa si el status no cambia."""
    admin = get_supabase_admin()

    existing = admin.table("properties").select("id, publisher_id, status").eq("id", property_id).maybe_single().execute()
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if property_row["publisher_id"] != publisher_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No sos el dueño de esta propiedad.")
    if property_row["status"] not in (PropertyStatus.published.value, PropertyStatus.expired.value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Solo se pueden renovar propiedades 'published' o 'expired' (esta está en '{property_row['status']}').",
        )

    now = datetime.now(timezone.utc)
    result = admin.table("properties").update({
        "status": PropertyStatus.published.value,
        "expires_at": (now + timedelta(days=RENEWAL_DAYS)).isoformat(),
        "renewed_at": now.isoformat(),
    }).eq("id", property_id).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo renovar la propiedad.")

    return result.data[0]