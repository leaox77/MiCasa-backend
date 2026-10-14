from datetime import datetime, timedelta, timezone

from app.core.supabase import get_supabase_admin
from app.schemas.properties import PropertyStatus
from app.services.notification_service import (
    _get_user_email,
    notify_favorites_status_change,
    notify_publisher_property_expired,
    notify_publisher_property_expiring_soon,
)

WARNING_DAYS_BEFORE = 10  # RN-012: aviso a los 50 días de 60


def run_daily_job() -> dict:
    """Job diario (RN-011 y RN-012). Es idempotente: se puede correr varias
    veces al día sin duplicar avisos ni expiraciones.

    1. Las propiedades 'published' con expires_at vencido pasan a 'expired' y
       se avisa al publicador y a quienes la tienen en favoritos.
    2. A las que vencen dentro de 10 días se les avisa una sola vez por email
       y notificación interna."""
    admin = get_supabase_admin()
    now = datetime.now(timezone.utc)

    expired_rows = (
        admin.table("properties")
        .select("id, title, publisher_id")
        .eq("status", PropertyStatus.published.value)
        .lt("expires_at", now.isoformat())
        .execute()
    ).data or []

    for row in expired_rows:
        admin.table("properties").update(
            {"status": PropertyStatus.expired.value}
        ).eq("id", row["id"]).execute()
        notify_publisher_property_expired(
            row["publisher_id"], row["id"], row["title"], _get_user_email(row["publisher_id"])
        )
        notify_favorites_status_change(row["id"], row["title"], PropertyStatus.expired.value)

    soon_rows = (
        admin.table("properties")
        .select("id, title, publisher_id, published_at, renewed_at")
        .eq("status", PropertyStatus.published.value)
        .gte("expires_at", now.isoformat())
        .lte("expires_at", (now + timedelta(days=WARNING_DAYS_BEFORE)).isoformat())
        .execute()
    ).data or []

    warned = 0
    for row in soon_rows:
        cycle_start = row.get("renewed_at") or row.get("published_at")
        already = (
            admin.table("notifications")
            .select("id")
            .eq("related_property_id", row["id"])
            .eq("type", "property_expiring_soon")
            .gte("created_at", cycle_start)
            .limit(1)
            .execute()
        ).data
        if already:
            continue
        notify_publisher_property_expiring_soon(
            row["publisher_id"], row["id"], row["title"], _get_user_email(row["publisher_id"])
        )
        warned += 1

    return {"expired": len(expired_rows), "warned": warned, "ran_at": now.isoformat()}
