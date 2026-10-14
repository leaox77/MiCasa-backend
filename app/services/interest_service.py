from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from app.services.notification_service import notify_buyer_interest_sent, notify_new_interest, _get_user_email


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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Propiedad no encontrada.",
        )

    existing = (
        admin.table("interest_requests")
        .select("id")
        .eq("property_id", property_id)
        .eq("buyer_id", buyer["id"])
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya enviaste tu interés para esta propiedad.",
        )

    result = admin.table("interest_requests").insert({
        "property_id": property_id,
        "buyer_id": buyer["id"],
        "message": message,
    }).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al registrar el interés.",
        )

    # Email del publicador desde auth.users (profiles no tiene columna email)
    publisher_email = _get_user_email(prop.data["publisher_id"])
    # Email del comprador también desde auth (buyer viene de profiles)
    buyer_email = _get_user_email(buyer["id"])

    notify_new_interest(
        publisher_id=prop.data["publisher_id"],
        property_id=property_id,
        prop_title=prop.data["title"],
        publisher_email=publisher_email,
        buyer_name=buyer.get("full_name", ""),
        buyer_email=buyer_email,
    )
    notify_buyer_interest_sent(buyer["id"], property_id, prop.data["title"])

    return {
        "id": result.data[0]["id"],
        "message": "Tu interés fue enviado. El publicador se contactará pronto.",
    }


def get_received_interests(publisher_id: str) -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("interest_requests")
        .select("id, created_at, message, properties!inner(id, title, publisher_id), profiles(full_name, phone)")
        .eq("properties.publisher_id", publisher_id)
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}