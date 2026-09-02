from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from datetime import datetime, timezone, timedelta


def get_my_properties(publisher_id: str, estado: str = None, page: int = 1, page_size: int = 20) -> dict:
    admin = get_supabase_admin()
    query = (
        admin.table("properties")
        .select("id, titulo, tipo, zona, precio, moneda, estado, created_at, updated_at, expires_at, view_count, interest_count", count="exact")
        .eq("publisher_id", publisher_id)
    )
    if estado:
        query = query.eq("estado", estado)

    start = (page - 1) * page_size
    query = query.order("created_at", desc=True).range(start, start + page_size - 1)
    result = query.execute()
    return {"data": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}


def get_my_metrics(publisher_id: str) -> dict:
    admin = get_supabase_admin()

    all_props = admin.table("properties").select("id, estado, view_count, interest_count, expires_at").eq("publisher_id", publisher_id).execute()
    rows = all_props.data or []

    now = datetime.now(timezone.utc)
    soon = now + timedelta(days=10)

    total_published = sum(1 for r in rows if r["estado"] == "published")
    total_views = sum(r.get("view_count", 0) or 0 for r in rows)
    total_interests = sum(r.get("interest_count", 0) or 0 for r in rows)
    active = sum(1 for r in rows if r["estado"] in ("published", "pending_review"))
    expiring_soon = sum(
        1 for r in rows
        if r["estado"] == "published"
        and r.get("expires_at")
        and datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00")) <= soon
    )

    return {
        "total_published": total_published,
        "total_views": total_views,
        "total_interests": total_interests,
        "active_properties": active,
        "expiring_soon": expiring_soon,
    }


def renew_property(property_id: str, publisher_id: str) -> dict:
    admin = get_supabase_admin()

    prop = admin.table("properties").select("*").eq("id", property_id).eq("publisher_id", publisher_id).maybe_single().execute()
    if not prop.data:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.")
    if prop.data["estado"] not in ("expired", "published"):
        raise HTTPException(status_code=400, detail="Solo podés renovar propiedades publicadas o expiradas.")

    now = datetime.now(timezone.utc)
    new_expires = (now + timedelta(days=60)).isoformat()

    result = admin.table("properties").update({
        "estado": "published",
        "expires_at": new_expires,
        "renewed_at": now.isoformat(),
    }).eq("id", property_id).execute()

    return result.data[0]