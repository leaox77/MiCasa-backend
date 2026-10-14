from collections import Counter

from app.core.supabase import get_supabase_admin


def get_zones() -> list[dict]:
    """Zonas con propiedades publicadas y su conteo, de mayor a menor."""
    admin = get_supabase_admin()
    rows = admin.table("properties").select("zone").eq("status", "published").execute().data or []
    counts = Counter(row["zone"] for row in rows if row.get("zone"))
    return [{"zone": zone, "count": count} for zone, count in counts.most_common()]


def get_stats() -> dict:
    """Cifras generales para la home (solo propiedades publicadas y publicadores activos)."""
    admin = get_supabase_admin()
    properties = admin.table("properties").select("zone", count="exact").eq("status", "published").execute()
    publishers = (
        admin.table("profiles")
        .select("id", count="exact")
        .eq("role", "publisher")
        .eq("is_active", True)
        .execute()
    )
    zones = {row["zone"] for row in (properties.data or []) if row.get("zone")}
    return {
        "total_properties": properties.count or 0,
        "total_publishers": publishers.count or 0,
        "zones_count": len(zones),
    }
