from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from app.services.notification_service import notify_new_interest


def express_interest(property_id: str, buyer: dict, message: str = None) -> dict:
    admin = get_supabase_admin()

    prop = (
        admin.table("properties")
        .select("id, title, publisher_id, status")
        .eq("id", property_id)
        .maybe_single()
        .execute()
    )
    if not prop.data or prop.data["status"] != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    existing = (
        admin.table("interest_requests")
        .select("id")
        .eq("property_id", property_id)
        .eq("buyer_id", buyer["id"])
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya enviaste tu interés para esta propiedad.")

    result = admin.table("interest_requests").insert({
        "property_id": property_id,
        "buyer_id": buyer["id"],
        "message": message,
    }).execute()

    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error al registrar el interés.")

    # OJO — Bug 1 sin arreglar acá (Parte 1, fuera de este alcance): este
    # select pide "email" a profiles, columna que no existe en la BD real.
    # El insert de arriba funciona igual; lo que se rompe es la
    # notificación al publicador.
    publisher = (
        admin.table("profiles")
        .select("email, full_name")
        .eq("id", prop.data["publisher_id"])
        .maybe_single()
        .execute()
    )
    if publisher.data:
        notify_new_interest(
            publisher_id=prop.data["publisher_id"],
            property_id=property_id,
            prop_title=prop.data["title"],
            publisher_email=publisher.data.get("email", ""),
            buyer_name=buyer.get("full_name", ""),
            buyer_email=buyer.get("email", ""),
        )

    return {"id": result.data[0]["id"], "message": "Tu interés fue enviado. El publicador se contactará pronto."}


def get_received_interests(publisher_id: str) -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("interest_requests")
        .select("id, created_at, message, properties(id, title), profiles(full_name, email, phone)")
        .eq("properties.publisher_id", publisher_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}