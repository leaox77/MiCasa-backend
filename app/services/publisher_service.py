from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from datetime import datetime, timezone, timedelta


def get_my_properties(publisher_id: str, page: int = 1, page_size: int = 20) -> dict:
    """Listado de propiedades del publisher logueado.

    TODO (pendiente coherencia de schema con Leandro): se sacó el parámetro
    `estado` (filtro) y las columnas `titulo`/`tipo`/`zona`/`precio`/`moneda`/
    `estado` del select porque `tipo`, `moneda` y `estado` no existen en la
    BD real. Sin `estado`, este listado no puede distinguir publicadas de
    borradores/pausadas — devuelve todo lo del publisher tal cual.
    """
    admin = get_supabase_admin()
    query = (
        admin.table("properties")
        .select("id, title, zone, price, created_at, updated_at, expires_at, view_count, interest_count", count="exact")
        .eq("publisher_id", publisher_id)
    )

    start = (page - 1) * page_size
    query = query.order("created_at", desc=True).range(start, start + page_size - 1)
    result = query.execute()
    return {"data": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}


def get_my_metrics(publisher_id: str) -> dict:
    """Métricas del dashboard del publisher.

    TODO / IMPORTANTE (pendiente coherencia de schema con Leandro):
    `total_published`, `active_properties` y `expiring_soon` dependían de
    `estado` (published/pending_review/expired). Sin esa columna no hay
    forma de calcularlos de verdad — quedan en `None` en vez de inventar un
    número, para que no se confunda con un dato real en el frontend.
    `total_views` y `total_interests` sí se pueden calcular porque
    `view_count`/`interest_count` sí existen en la BD real.
    """
    admin = get_supabase_admin()

    all_props = admin.table("properties").select("id, view_count, interest_count, expires_at").eq("publisher_id", publisher_id).execute()
    rows = all_props.data or []

    total_views = sum(r.get("view_count", 0) or 0 for r in rows)
    total_interests = sum(r.get("interest_count", 0) or 0 for r in rows)

    return {
        "total_published": None,  # TODO: requiere columna "status"
        "total_views": total_views,
        "total_interests": total_interests,
        "active_properties": None,  # TODO: requiere columna "status"
        "expiring_soon": None,  # TODO: requiere columna "status"
    }


def renew_property(property_id: str, publisher_id: str) -> dict:
    """TODO (pendiente coherencia de schema con Leandro): antes validaba
    que la propiedad estuviera 'expired' o 'published' y la volvía a poner
    en 'published'. Sin columna "status" no hay nada que chequear ni que
    setear — se deshabilita explícitamente en vez de renovar a ciegas."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Renovación no disponible: falta la columna 'status' en el schema real (pendiente de definir con Leandro).",
    )