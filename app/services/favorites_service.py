from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin


def list_favorites(user_id: str) -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("favorites")
        .select("id, created_at, properties(id, title, price, zone, city)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}


def add_favorite(user_id: str, property_id: str) -> dict:
    admin = get_supabase_admin()

    prop = (
        admin.table("properties")
        .select("id, status")
        .eq("id", property_id)
        .maybe_single()
        .execute()
    )
    if not prop.data or prop.data["status"] != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    existing = (
        admin.table("favorites")
        .select("id")
        .eq("user_id", user_id)
        .eq("property_id", property_id)
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta propiedad ya está en tus favoritos.")

    result = admin.table("favorites").insert({
        "user_id": user_id,
        "property_id": property_id,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar el favorito.")

    return result.data[0]


def remove_favorite(user_id: str, property_id: str) -> None:
    admin = get_supabase_admin()
    existing = (
        admin.table("favorites")
        .select("id")
        .eq("user_id", user_id)
        .eq("property_id", property_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Esta propiedad no está en tus favoritos.")

    admin.table("favorites").delete().eq("user_id", user_id).eq("property_id", property_id).execute()