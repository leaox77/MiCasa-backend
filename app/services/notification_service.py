from app.core.supabase import get_supabase_admin
from app.core.config import get_settings
import resend

settings = get_settings()
resend.api_key = settings.resend_api_key


def send_email(to: str, subject: str, html: str) -> bool:
    """Envía un email transaccional vía Resend."""
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


def create_notification(
    user_id: str,
    notif_type: str,
    title: str,
    body: str,
    property_id: str = None,
) -> None:
    """Crea una notificación interna en la BD."""
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
        pass  # Notificaciones no deben bloquear el flujo principal


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
        <p>Contactalo directamente para continuar la conversación.</p>
        """,
    )


def notify_favorite_price_change(property_id: str, prop_title: str, old_price: float, new_price: float, currency: str) -> None:
    """Notifica a todos los compradores que tienen esta propiedad en favoritos."""
    admin = get_supabase_admin()
    favorites = admin.table("favorites").select("user_id").eq("property_id", property_id).execute()

    for fav in (favorites.data or []):
        user_id = fav["user_id"]
        profile = admin.table("profiles").select("full_name, email").eq("id", user_id).single().execute()
        if not profile.data:
            continue

        create_notification(
            user_id=user_id,
            notif_type="favorite_price_change",
            title="Cambio de precio en un favorito",
            body=f"'{prop_title}' cambió de {old_price:,.0f} a {new_price:,.0f} {currency}.",
            property_id=property_id,
        )
        send_email(
            to=profile.data.get("email", ""),
            subject=f"💰 Cambio de precio — {prop_title}",
            html=f"<p>El precio de <strong>{prop_title}</strong> que tenés en favoritos cambió de <strong>{old_price:,.0f} {currency}</strong> a <strong>{new_price:,.0f} {currency}</strong>.</p>",
        )

def notify_admin_new_property_pending(property_id: str, prop_title: str, publisher_id: str) -> None:
    """Notifica a todos los admins que una propiedad quedó pendiente de revisión."""
    admin = get_supabase_admin()
    admins = admin.table("profiles").select("id, email").eq("role", "admin").execute()

    for adm in (admins.data or []):
        create_notification(
            user_id=adm["id"],
            notif_type="property_pending_review",
            title="Nueva propiedad pendiente de revisión",
            body=f"'{prop_title}' fue enviada a revisión y espera tu aprobación.",
            property_id=property_id,
        )
        send_email(
            to=adm.get("email", ""),
            subject="🕓 Nueva propiedad pendiente de revisión — Mi Casa",
            html=f"<p>Una nueva propiedad, <strong>{prop_title}</strong>, fue enviada a revisión y espera tu aprobación.</p>",
        )