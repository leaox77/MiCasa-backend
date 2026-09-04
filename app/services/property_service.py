from decimal import Decimal
from enum import Enum

from fastapi import HTTPException, UploadFile, status

from app.core.supabase import get_supabase_admin
from app.schemas.properties import (
    OrderBy,
    PropertyCreate,
    PropertyListItem,
    PropertySearchParams,
    PropertySearchResponse,
    PropertyStatus,
    PropertyStatusUpdate,
    PropertyUpdate,
)
from app.services import storage_service
from app.services.notification_service import (
    notify_admin_new_property_pending,
    notify_favorite_price_change,
)


def _serialize_for_supabase(payload: dict) -> dict:
    """Convierte Enum y Decimal de Pydantic a algo JSON-serializable para
    el cliente de Supabase (que usa json.dumps por debajo)."""
    clean = {}
    for key, value in payload.items():
        if isinstance(value, Enum):
            clean[key] = value.value
        elif isinstance(value, Decimal):
            clean[key] = float(value)
        else:
            clean[key] = value
    return clean


# Transiciones de status permitidas. "pending_review" NO aparece en
# _ADMIN_TRANSITIONS a propósito: aprobar/rechazar tiene sus propios
# endpoints dedicados en /admin (admin_service.py), que además auditan
# la acción. Este mapa es para pausar/reactivar/reenviar/borrar.
_PUBLISHER_TRANSITIONS: dict[str, set[str]] = {
    PropertyStatus.draft.value: {PropertyStatus.pending_review.value},
    PropertyStatus.rejected.value: {PropertyStatus.pending_review.value},
    PropertyStatus.published.value: {PropertyStatus.paused.value},
    PropertyStatus.paused.value: {PropertyStatus.published.value},
}

_ADMIN_TRANSITIONS: dict[str, set[str]] = {
    PropertyStatus.published.value: {PropertyStatus.paused.value, PropertyStatus.deleted.value},
    PropertyStatus.paused.value: {PropertyStatus.published.value, PropertyStatus.deleted.value},
    PropertyStatus.draft.value: {PropertyStatus.deleted.value},
    PropertyStatus.rejected.value: {PropertyStatus.deleted.value},
    PropertyStatus.expired.value: {PropertyStatus.deleted.value},
}


def create_property(publisher_id: str, data: PropertyCreate, submit: bool = False) -> dict:
    """Crea una propiedad. status inicial: 'pending_review' si submit=True
    (y se notifica a los admins), 'draft' si no."""
    admin = get_supabase_admin()

    payload = _serialize_for_supabase(data.model_dump())
    payload["publisher_id"] = publisher_id
    payload["status"] = (
        PropertyStatus.pending_review.value if submit else PropertyStatus.draft.value
    )

    result = admin.table("properties").insert(payload).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo crear la propiedad.",
        )

    property_row = result.data[0]

    if submit:
        notify_admin_new_property_pending(
            property_id=property_row["id"],
            prop_title=property_row["title"],
            publisher_id=publisher_id,
        )

    return property_row


def get_property(property_id: str, requesting_user: dict | None) -> dict:
    """Detalle de una propiedad. Si no está 'published', solo la ve el
    dueño o un admin. A cualquier otro (o anónimo) se le devuelve 404, no
    403 — no reveles que el id existe."""
    admin = get_supabase_admin()

    result = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = result.data

    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    if property_row["status"] != PropertyStatus.published.value:
        is_owner = requesting_user is not None and requesting_user.get("id") == property_row["publisher_id"]
        is_admin = requesting_user is not None and requesting_user.get("role") == "admin"
        if not (is_owner or is_admin):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    images = (
        admin.table("property_images")
        .select("*")
        .eq("property_id", property_id)
        .order("order_index")
        .execute()
    )
    property_row["images"] = images.data or []

    publisher = (
        admin.table("profiles")
        .select("id, full_name, publisher_type")
        .eq("id", property_row["publisher_id"])
        .maybe_single()
        .execute()
    )
    property_row["publisher"] = publisher.data

    return property_row


def update_property(property_id: str, publisher_id: str, data: PropertyUpdate) -> dict:
    """Edita una propiedad. Solo el dueño puede editarla. Si cambia el
    precio, el historial se registra A MANO en property_price_history —
    el trigger handle_price_change existe en la BD pero nunca estuvo
    adjuntado a la tabla, y encima está roto (ver migración). No confiar
    en que la BD lo hace sola."""
    admin = get_supabase_admin()

    existing = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    if property_row["publisher_id"] != publisher_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No sos el dueño de esta propiedad.")

    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        return property_row

    new_price = update_fields.get("price")
    price_changed = new_price is not None and Decimal(str(new_price)) != Decimal(str(property_row["price"]))

    payload = _serialize_for_supabase(update_fields)

    result = admin.table("properties").update(payload).eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la propiedad.",
        )

    updated_row = result.data[0]

    if price_changed:
        admin.table("property_price_history").insert({
            "property_id": property_id,
            "old_price": float(property_row["price"]),
            "new_price": float(updated_row["price"]),
            "currency": updated_row["currency"],
            "changed_by": publisher_id,
        }).execute()

        notify_favorite_price_change(
            property_id=property_id,
            prop_title=updated_row["title"],
            old_price=float(property_row["price"]),
            new_price=float(updated_row["price"]),
            currency=updated_row["currency"],
        )

    return updated_row


def change_property_status(property_id: str, actor: dict, data: PropertyStatusUpdate) -> dict:
    """Pausar/reactivar/reenviar a revisión/borrar. Aprobar y rechazar una
    propiedad 'pending_review' NO pasa por acá — son los endpoints
    dedicados /admin/properties/{id}/approve y /reject (admin_service.py)."""
    admin = get_supabase_admin()

    existing = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    current_status = property_row["status"]
    is_owner = property_row["publisher_id"] == actor["id"]
    is_admin = actor.get("role") == "admin"

    if is_admin:
        allowed = _ADMIN_TRANSITIONS.get(current_status, set())
    elif is_owner:
        allowed = _PUBLISHER_TRANSITIONS.get(current_status, set())
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No sos el dueño de esta propiedad.")

    new_status_value = data.new_status.value
    if new_status_value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transición inválida: '{current_status}' -> '{new_status_value}'. "
                "Para aprobar o rechazar una propiedad 'pending_review' usá los "
                "endpoints de /admin."
            ),
        )

    payload = {"status": new_status_value}
    if current_status == PropertyStatus.rejected.value and new_status_value == PropertyStatus.pending_review.value:
        payload["rejection_reason"] = None  # reenvío: limpiar el motivo de rechazo anterior

    result = admin.table("properties").update(payload).eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar el estado de la propiedad.",
        )

    updated_row = result.data[0]

    if new_status_value == PropertyStatus.pending_review.value:
        notify_admin_new_property_pending(
            property_id=property_id,
            prop_title=updated_row["title"],
            publisher_id=property_row["publisher_id"],
        )

    return updated_row


def _get_owned_property_or_404(property_id: str, publisher_id: str, admin) -> dict:
    """Chequeo de dueño compartido por las 3 funciones de imágenes de abajo."""
    result = admin.table("properties").select("id, publisher_id").eq("id", property_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")
    if result.data["publisher_id"] != publisher_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No sos el dueño de esta propiedad.")
    return result.data


def add_property_image(property_id: str, publisher_id: str, file: UploadFile) -> dict:
    """Valida dueño, sube la foto vía storage_service y la inserta en
    property_images.

    OJO — Bug 2 pendiente (Parte 1, sin tocar acá): este insert NO manda
    "storage_path", que en la BD real es NOT NULL. Cada subida de foto va
    a fallar por violación de constraint hasta que se arregle esto."""
    admin = get_supabase_admin()
    _get_owned_property_or_404(property_id, publisher_id, admin)

    current_count = (
        admin.table("property_images")
        .select("id", count="exact")
        .eq("property_id", property_id)
        .execute()
    ).count or 0

    uploaded = storage_service.upload_property_image(property_id, file, current_count)

    result = admin.table("property_images").insert({
        "property_id": property_id,
        "url": uploaded["url"],
        "order_index": uploaded["order_index"],
    }).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo guardar la imagen.",
        )

    return result.data[0]


def remove_property_image(property_id: str, publisher_id: str, image_id: str) -> None:
    admin = get_supabase_admin()
    _get_owned_property_or_404(property_id, publisher_id, admin)
    storage_service.delete_property_image(property_id, image_id)


def reorder_property_images(property_id: str, publisher_id: str, image_ids_in_order: list[str]) -> None:
    admin = get_supabase_admin()
    _get_owned_property_or_404(property_id, publisher_id, admin)
    storage_service.reorder_property_images(property_id, image_ids_in_order)


def _to_list_item(row: dict) -> PropertyListItem:
    """Arma un PropertyListItem a partir de una fila de properties con
    property_images embebido (ver select() en search_properties)."""
    images = row.get("property_images") or []
    main_photo = None
    if images:
        first = min(images, key=lambda img: img.get("order_index", 0))
        main_photo = first.get("url")

    tags = []
    if row.get("is_presale"):
        tags.append("presale")
    if row.get("is_investment"):
        tags.append("investment")

    return PropertyListItem(
        id=row["id"],
        main_photo=main_photo,
        price=row["price"],
        currency=row["currency"],
        property_type=row["property_type"],
        zone=row["zone"],
        city=row["city"],
        bedrooms=row["bedrooms"],
        area_m2=row["area_m2"],
        tags=tags,
    )


def search_properties(params: PropertySearchParams) -> PropertySearchResponse:
    """Listado público con filtros acumulables (AND), paginación y orden.
    SOLO devuelve propiedades 'published' — filtro restaurado."""
    admin = get_supabase_admin()

    query = (
        admin.table("properties")
        .select("*, property_images(url, order_index)", count="exact")
        .eq("status", PropertyStatus.published.value)
    )

    if params.price_min is not None:
        query = query.gte("price", float(params.price_min))
    if params.price_max is not None:
        query = query.lte("price", float(params.price_max))
    if params.property_type is not None:
        query = query.eq("property_type", params.property_type.value)
    if params.currency is not None:
        query = query.eq("currency", params.currency.value)
    if params.zone is not None:
        query = query.ilike("zone", f"%{params.zone}%")
    if params.city is not None:
        query = query.ilike("city", f"%{params.city}%")
    if params.bedrooms is not None:
        query = query.eq("bedrooms", params.bedrooms)
    if params.area_m2_min is not None:
        query = query.gte("area_m2", params.area_m2_min)
    if params.area_m2_max is not None:
        query = query.lte("area_m2", params.area_m2_max)
    if params.has_garage is not None:
        query = query.eq("has_garage", params.has_garage)
    if params.age_years is not None:
        query = query.lte("age_years", params.age_years)
    if params.is_presale is not None:
        query = query.eq("is_presale", params.is_presale)

    if params.order == OrderBy.price_asc:
        query = query.order("price", desc=False)
    elif params.order == OrderBy.price_desc:
        query = query.order("price", desc=True)
    else:
        query = query.order("created_at", desc=True)

    start = (params.page - 1) * params.page_size
    end = start + params.page_size - 1
    query = query.range(start, end)

    result = query.execute()
    rows = result.data or []
    total = result.count or 0

    return PropertySearchResponse(
        results=[_to_list_item(row) for row in rows],
        total=total,
        page=params.page,
        page_size=params.page_size,
    )