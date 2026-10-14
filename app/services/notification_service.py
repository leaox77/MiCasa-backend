from app.core.supabase import get_supabase_admin
from app.core.config import get_settings
import resend

settings = get_settings()
resend.api_key = settings.resend_api_key


def send_email(to: str, subject: str, html: str) -> bool:
    if not to:
        return False
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": to,
            "subject": subject,
            "html": html,
        })
        return True
    except Exception:
        return False


def _get_user_email(user_id: str) -> str:
    """Email desde auth.users via admin SDK — profiles no tiene columna email."""
    admin = get_supabase_admin()
    try:
        response = admin.auth.admin.get_user_by_id(user_id)
        return response.user.email or ""
    except Exception:
        return ""


def create_notification(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    property_id: str = None,
) -> None:
    admin = get_supabase_admin()
    data = {
        "user_id": user_id,
        "type": notif_type,
        "title": title,
        "body": body,
    }
    if property_id:
        data["related_property_id"] = property_id
    try:
        admin.table("notifications").insert(data).execute()
    except Exception:
        pass


def notify_publisher_property_approved(publisher_id: str, property_id: str, title: str, email: str) -> None:
    create_notification(
        user_id=publisher_id,
        notif_type="property_approved",
        title="Tu propiedad fue aprobada",
        body=f"'{title}' ya es visible públicamente en Mi Casa.",
        property_id=property_id,
    )
    send_email(
        to=email,
        subject="✅ Tu propiedad fue aprobada — Mi Casa",
        html=f"<p>Tu publicación <strong>{title}</strong> fue aprobada y ya aparece en el listado.</p>",
    )


def notify_publisher_property_rejected(publisher_id: str, property_id: str, title: str, email: str, reason: str) -> None:
    create_notification(
        user_id=publisher_id,
        notif_type="property_rejected",
        title="Tu propiedad fue rechazada",
        body=f"'{title}' fue rechazada. Motivo: {reason}",
        property_id=property_id,
    )
    send_email(
        to=email,
        subject="❌ Tu propiedad necesita correcciones — Mi Casa",
        html=f"<p>Tu publicación <strong>{title}</strong> fue rechazada.</p><p><strong>Motivo:</strong> {reason}</p><p>Podés corregirla y reenviarla desde tu panel.</p>",
    )


def notify_new_interest(publisher_id: str, property_id: str, prop_title: str, publisher_email: str, buyer_name: str, buyer_email: str) -> None:
    create_notification(
        user_id=publisher_id,
        notif_type="new_interest",
        title="Nuevo interesado en tu propiedad",
        body=f"{buyer_name} está interesado en '{prop_title}'.",
        property_id=property_id,
    )
    send_email(
        to=publisher_email,
        subject=f"🏠 Nuevo interesado en {prop_title} — Mi Casa",
        html=f"""
        <p>Tenés un nuevo interesado en <strong>{prop_title}</strong>.</p>
        <p><strong>Nombre:</strong> {buyer_name}</p>
        <p><strong>Email:</strong> {buyer_email}</p>
        """,
    )


def notify_favorite_price_change(property_id: str, prop_title: str, old_price: float, new_price: float, currency: str) -> None:
    admin = get_supabase_admin()
    favorites = admin.table("favorites").select("user_id").eq("property_id", property_id).execute()

    for fav in (favorites.data or []):
        user_id = fav["user_id"]
        email = _get_user_email(user_id)  # ← corregido: desde auth, no desde profiles

        create_notification(
            user_id=user_id,
            notif_type="favorite_price_change",
            title="Cambio de precio en un favorito",
            body=f"'{prop_title}' cambió de {old_price:,.0f} a {new_price:,.0f} {currency}.",
            property_id=property_id,
        )
        send_email(
            to=email,
            subject=f"💰 Cambio de precio — {prop_title}",
            html=f"<p>El precio de <strong>{prop_title}</strong> que tenés en favoritos cambió de <strong>{old_price:,.0f} {currency}</strong> a <strong>{new_price:,.0f} {currency}</strong>.</p>",
        )


def notify_admin_new_property_pending(property_id: str, prop_title: str, publisher_id: str) -> None:
    admin = get_supabase_admin()
    admins = admin.table("profiles").select("id").eq("role", "admin").execute()

    for adm in (admins.data or []):
        email = _get_user_email(adm["id"])  # ← corregido
        create_notification(
            user_id=adm["id"],
            notif_type="property_pending_review",
            title="Nueva propiedad pendiente de revisión",
            body=f"'{prop_title}' fue enviada a revisión y espera tu aprobación.",
            property_id=property_id,
        )
        send_email(
            to=email,
            subject="🕓 Nueva propiedad pendiente de revisión — Mi Casa",
            html=f"<p>Una nueva propiedad, <strong>{prop_title}</strong>, fue enviada a revisión.</p>",
        )

def notify_buyer_interest_sent(buyer_id: str, property_id: str, prop_title: str) -> None:
    create_notification(
        user_id=buyer_id,
        notif_type="interest_sent",
        title="Tu interés fue enviado",
        body=f"Tu interés en '{prop_title}' fue enviado. El publicador se contactará pronto.",
        property_id=property_id,
    )


def notify_admins_new_report(property_id: str, prop_title: str, reason: str) -> None:
    admin = get_supabase_admin()
    admins = admin.table("profiles").select("id").eq("role", "admin").execute()
    for adm in (admins.data or []):
        create_notification(
            user_id=adm["id"],
            notif_type="new_report",
            title="Nueva denuncia recibida",
            body=f"Nueva denuncia sobre la propiedad '{prop_title}'. Categoría: {reason}.",
            property_id=property_id,
        )


def notify_reporter_report_received(reporter_id: str, property_id: str) -> None:
    create_notification(
        user_id=reporter_id,
        notif_type="report_received",
        title="Denuncia recibida",
        body="Tu denuncia fue recibida. El equipo la revisará a la brevedad.",
        property_id=property_id,
    )


def notify_publisher_property_expired(publisher_id: str, property_id: str, title: str, email: str) -> None:
    create_notification(
        user_id=publisher_id,
        notif_type="property_expired",
        title="Tu publicación expiró",
        body=f"'{title}' expiró y ya no es visible. Podés renovarla desde tu panel.",
        property_id=property_id,
    )
    send_email(
        to=email,
        subject="Tu publicación expiró — Mi Casa",
        html=f"<p>Tu publicación <strong>{title}</strong> expiró y ya no es visible. Podés renovarla desde tu panel.</p>",
    )


def notify_publisher_property_expiring_soon(publisher_id: str, property_id: str, title: str, email: str) -> None:
    create_notification(
        user_id=publisher_id,
        notif_type="property_expiring_soon",
        title="Tu publicación está por expirar",
        body=f"'{title}' expira en 10 días. Renovala desde tu panel para que siga visible.",
        property_id=property_id,
    )
    send_email(
        to=email,
        subject="Tu publicación expira pronto — Mi Casa",
        html=f"<p>Tu publicación <strong>{title}</strong> expira en 10 días. Renovala desde tu panel para que siga visible.</p>",
    )


STATUS_LABELS = {"paused": "pausada", "expired": "expirada", "deleted": "eliminada"}


def notify_favorites_status_change(property_id: str, prop_title: str, new_status: str) -> None:
    """RN-033: avisa a quienes tienen la propiedad en favoritos cuando pasa a
    pausada, expirada o eliminada."""
    label = STATUS_LABELS.get(new_status)
    if label is None:
        return
    admin = get_supabase_admin()
    favorites = admin.table("favorites").select("user_id").eq("property_id", property_id).execute()
    for fav in (favorites.data or []):
        create_notification(
            user_id=fav["user_id"],
            notif_type="favorite_status_change",
            title="Un favorito cambió de estado",
            body=f"La propiedad '{prop_title}' que tenés en favoritos fue {label}.",
            property_id=property_id,
        )
        send_email(
            to=_get_user_email(fav["user_id"]),
            subject=f"Tu favorito fue {label} — Mi Casa",
            html=f"<p>La propiedad <strong>{prop_title}</strong> que tenés en favoritos fue {label}.</p>",
        )


def notify_user_suspended(email: str, reason: str) -> None:
    send_email(
        to=email,
        subject="Tu cuenta en Mi Casa fue suspendida",
        html=f"<p>Tu cuenta en Mi Casa fue suspendida.</p><p><strong>Motivo:</strong> {reason}</p><p>Contactá al soporte para más información.</p>",
    )


def list_notifications(user_id: str) -> dict:
    admin = get_supabase_admin()
    result = (
        admin.table("notifications")
        .select("id, type, title, body, is_read, related_property_id, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    data = result.data or []
    unread_count = sum(1 for n in data if not n.get("is_read"))
    return {"data": data, "unread_count": unread_count}


def mark_as_read(notification_id: str, user_id: str) -> dict:
    admin = get_supabase_admin()

    existing = (
        admin.table("notifications")
        .select("id")
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not existing.data:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notificación no encontrada.",
        )

    result = (
        admin.table("notifications")
        .update({"is_read": True})
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .execute()
    )
    return result.data[0]


def mark_all_as_read(user_id: str) -> dict:
    admin = get_supabase_admin()
    admin.table("notifications").update({"is_read": True}).eq("user_id", user_id).eq("is_read", False).execute()
    return {"message": "Todas las notificaciones marcadas como leídas."}