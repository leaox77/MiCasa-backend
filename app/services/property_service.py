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
    PropertyUpdate,
)
from app.services import storage_service
from app.services.notification_service import (
    notify_admin_new_property_pending,
    notify_favorite_price_change,
    notify_publisher_property_approved,
    notify_publisher_property_rejected,
)


# Transiciones permitidas por rol. Solo cubre lo que pide el sprint planning
# (paused/pending_review para publisher, published/rejected para admin) — no
# es una máquina de estados completa por (origen -> destino); ver nota abajo.
PUBLISHER_ALLOWED_TARGETS = {PropertyStatus.paused.value, PropertyStatus.pending_review.value}
ADMIN_ALLOWED_TARGETS = {PropertyStatus.published.value, PropertyStatus.rejected.value}


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


def create_property(publisher_id: str, data: PropertyCreate, submit: bool = False) -> dict:
    """Crea una propiedad en 'draft'. Si submit=True, la pasa directo a
    'pending_review' y avisa a los admins (wizard de 3 pasos del frontend)."""
    admin = get_supabase_admin()

    payload = _serialize_for_supabase(data.model_dump())
    payload["publisher_id"] = publisher_id
    payload["estado"] = (
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
            prop_title=property_row["titulo"],
            publisher_id=publisher_id,
        )

    return property_row


def get_property(property_id: str, requesting_user: dict | None) -> dict:
    """Detalle de una propiedad. Si no está 'published', solo la ve el
    publisher dueño o un admin — 404 (no 403) en cualquier otro caso, para
    no filtrar si la propiedad existe."""
    admin = get_supabase_admin()

    result = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = result.data

    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    is_owner = requesting_user is not None and requesting_user["id"] == property_row["publisher_id"]
    is_admin = requesting_user is not None and requesting_user["role"] == "admin"

    if property_row["estado"] != PropertyStatus.published.value and not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    images = (
        admin.table("property_images")
        .select("*")
        .eq("property_id", property_id)
        .order("order_index")
        .execute()
    )
    property_row["imagenes"] = images.data or []

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
    precio, registra el cambio en property_status_history y notifica a
    quienes la tienen en favoritos."""
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

    new_price = update_fields.get("precio")
    price_changed = new_price is not None and Decimal(str(new_price)) != Decimal(str(property_row["precio"]))

    payload = _serialize_for_supabase(update_fields)

    result = admin.table("properties").update(payload).eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo actualizar la propiedad.",
        )

    updated_row = result.data[0]

    if price_changed:
        admin.table("property_status_history").insert({
            "property_id": property_id,
            "old_status": property_row["estado"],
            "new_status": updated_row["estado"],
            "old_price": float(property_row["precio"]),
            "new_price": float(updated_row["precio"]),
            "changed_by": publisher_id,
        }).execute()

        notify_favorite_price_change(
            property_id=property_id,
            prop_title=updated_row["titulo"],
            old_price=float(property_row["precio"]),
            new_price=float(updated_row["precio"]),
            currency=updated_row["moneda"],
        )

    return updated_row


def change_property_status(
    property_id: str,
    actor: dict,
    new_status: PropertyStatus,
    reason: str | None = None,
) -> dict:
    """Cambia el estado de una propiedad según el rol del actor y notifica
    al publisher si el resultado es 'published' o 'rejected'."""
    admin = get_supabase_admin()

    existing = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = existing.data
    if not property_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Propiedad no encontrada.")

    role = actor["role"]
    new_status_value = new_status.value

    if role == "publisher":
        if property_row["publisher_id"] != actor["id"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No sos el dueño de esta propiedad.")
        if new_status_value not in PUBLISHER_ALLOWED_TARGETS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Como publicador solo podés pausar la propiedad o reenviarla a revisión.",
            )
    elif role == "admin":
        if new_status_value not in ADMIN_ALLOWED_TARGETS:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Como admin solo podés publicar o rechazar propiedades.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenés permisos para cambiar el estado de esta propiedad.",
        )

    old_status_value = property_row["estado"]

    result = admin.table("properties").update({"estado": new_status_value}).eq("id", property_id).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No se pudo cambiar el estado de la propiedad.",
        )

    updated_row = result.data[0]

    admin.table("property_status_history").insert({
        "property_id": property_id,
        "old_status": old_status_value,
        "new_status": new_status_value,
        "changed_by": actor["id"],
    }).execute()

    publisher = (
        admin.table("profiles")
        .select("email")
        .eq("id", property_row["publisher_id"])
        .maybe_single()
        .execute()
    )
    publisher_email = (publisher.data or {}).get("email", "")

    if new_status_value == PropertyStatus.published.value:
        notify_publisher_property_approved(
            publisher_id=property_row["publisher_id"],
            property_id=property_id,
            title=updated_row["titulo"],
            email=publisher_email,
        )
    elif new_status_value == PropertyStatus.rejected.value:
        notify_publisher_property_rejected(
            publisher_id=property_row["publisher_id"],
            property_id=property_id,
            title=updated_row["titulo"],
            email=publisher_email,
            reason=reason or "No se especificó un motivo.",
        )

    return updated_row


def pause_property(property_id: str, publisher_id: str) -> dict:
    """Atajo sobre change_property_status para pausar sin borrar (US-014)."""
    return change_property_status(
        property_id=property_id,
        actor={"id": publisher_id, "role": "publisher"},
        new_status=PropertyStatus.paused,
        reason=None,
    )


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
    property_images. Devuelve la fila insertada."""
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
    foto_principal = None
    if images:
        primera = min(images, key=lambda img: img.get("order_index", 0))
        foto_principal = primera.get("url")

    etiquetas = []
    if row.get("es_preventa"):
        etiquetas.append("preventa")
    if row.get("ideal_inversion"):
        etiquetas.append("inversion")

    return PropertyListItem(
        id=row["id"],
        foto_principal=foto_principal,
        tipo=row["tipo"],
        precio=row["precio"],
        moneda=row["moneda"],
        zona=row["zona"],
        habitaciones=row["habitaciones"],
        m2=row["m2"],
        etiquetas=etiquetas,
    )


def search_properties(params: PropertySearchParams) -> PropertySearchResponse:
    """Listado público con filtros acumulables (AND), paginación y orden.
    Solo devuelve propiedades 'published'."""
    admin = get_supabase_admin()

    query = (
        admin.table("properties")
        .select("*, property_images(url, order_index)", count="exact")
        .eq("estado", PropertyStatus.published.value)
    )

    if params.tipo is not None:
        query = query.eq("tipo", params.tipo.value)
    if params.precio_min is not None:
        query = query.gte("precio", float(params.precio_min))
    if params.precio_max is not None:
        query = query.lte("precio", float(params.precio_max))
    if params.moneda is not None:
        query = query.eq("moneda", params.moneda.value)
    if params.zona is not None:
        query = query.ilike("zona", f"%{params.zona}%")
    if params.habitaciones is not None:
        query = query.eq("habitaciones", params.habitaciones)
    if params.m2_min is not None:
        query = query.gte("m2", params.m2_min)
    if params.m2_max is not None:
        query = query.lte("m2", params.m2_max)
    if params.garaje is not None:
        query = query.eq("garaje", params.garaje)
    if params.antiguedad is not None:
        query = query.lte("antiguedad", params.antiguedad)
    if params.preventa is not None:
        query = query.eq("es_preventa", params.preventa)

    if params.orden == OrderBy.precio_asc:
        query = query.order("precio", desc=False)
    elif params.orden == OrderBy.precio_desc:
        query = query.order("precio", desc=True)
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