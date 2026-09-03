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
    PropertyUpdate,
)
from app.services import storage_service
from app.services.notification_service import (
    notify_admin_new_property_pending,
    notify_favorite_price_change,
    notify_publisher_property_approved,
    notify_publisher_property_rejected,
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


def create_property(publisher_id: str, data: PropertyCreate, submit: bool = False) -> dict:
    """Crea una propiedad.

    TODO (pendiente coherencia de schema con Leandro): sin columna "status"
    en la BD real, no hay forma de guardar si la propiedad quedó en
    draft/pending_review. El insert de abajo NO fija ningún estado — el
    parámetro `submit` hoy solo controla si se avisa al admin, no afecta
    lo que se guarda en la fila.
    """
    admin = get_supabase_admin()

    payload = _serialize_for_supabase(data.model_dump())
    payload["publisher_id"] = publisher_id

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
    """Detalle de una propiedad.

    TODO / IMPORTANTE (pendiente coherencia de schema con Leandro): antes,
    esta función ocultaba propiedades no "published" a quien no fuera el
    dueño o un admin. Sin columna "status" real, ESE CONTROL DE ACCESO YA
    NO EXISTE: cualquiera que tenga o adivine un id puede ver cualquier
    propiedad, incluidas las que deberían ser borrador. Esto hay que
    resolverlo junto con la decisión de "status" — no es solo un detalle
    de nombres.
    """
    admin = get_supabase_admin()

    result = admin.table("properties").select("*").eq("id", property_id).maybe_single().execute()
    property_row = result.data

    if not property_row:
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
    precio, el trigger de BD `handle_price_change` ya inserta el registro
    en `property_price_history` automáticamente — por eso este código ya
    NO hace ese insert a mano (antes apuntaba a `property_status_history`,
    que ni siquiera existe en la BD real; era redundante con el trigger
    además de estar mal apuntada)."""
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
        notify_favorite_price_change(
            property_id=property_id,
            prop_title=updated_row["title"],
            old_price=float(property_row["price"]),
            new_price=float(updated_row["price"]),
            # TODO (pendiente coherencia de schema): no hay columna "currency"
            # en la BD real. Se hardcodea "BOB" hasta que se resuelva.
            currency="BOB",
        )

    return updated_row


def change_property_status(*args, **kwargs):
    """TODO (pendiente coherencia de schema con Leandro): esta función no
    puede funcionar sin una columna "status" en la BD real. Antes de
    reescribirla hay que decidir si esa columna se agrega. La dejo
    explícitamente deshabilitada en vez de simular un comportamiento que
    no persiste nada, para no esconder el problema."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Cambio de estado no disponible: falta la columna 'status' en el schema real (pendiente de definir con Leandro).",
    )


def pause_property(*args, **kwargs):
    """Atajo sobre change_property_status — ver TODO de esa función."""
    return change_property_status()


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
        zone=row["zone"],
        city=row["city"],
        bedrooms=row["bedrooms"],
        area_m2=row["area_m2"],
        tags=tags,
    )


def search_properties(params: PropertySearchParams) -> PropertySearchResponse:
    """Listado público con filtros acumulables (AND), paginación y orden.

    TODO / IMPORTANTE (pendiente coherencia de schema con Leandro): antes
    este listado filtraba SOLO propiedades "published". Sin columna
    "status" real, ese filtro se sacó — hoy este endpoint devuelve TODAS
    las propiedades de la tabla, incluidas las que deberían ser borrador.
    No es un tema de nombres, es una regla de negocio que quedó sin poder
    aplicarse.
    """
    admin = get_supabase_admin()

    query = admin.table("properties").select("*, property_images(url, order_index)", count="exact")

    if params.price_min is not None:
        query = query.gte("price", float(params.price_min))
    if params.price_max is not None:
        query = query.lte("price", float(params.price_max))
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