import io
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from PIL import Image

from app.core.supabase import get_supabase_admin

BUCKET_NAME = "property-images"

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
MAX_IMAGES_PER_PROPERTY = 15
# Es una URL FIRMADA (no pública) — expira. Ver nota al final del bloque.
SIGNED_URL_EXPIRES_IN = 60 * 60 * 24 * 365  # 1 año, en segundos


def _compress_image(raw_bytes: bytes, content_type: str) -> bytes:
    """Comprime la imagen a calidad 80% preservando su formato original.
    PNG es sin pérdida, así que ahí 'calidad 80%' se traduce en optimización
    de compresión en vez de un parámetro quality (Pillow no lo soporta para PNG)."""
    image = Image.open(io.BytesIO(raw_bytes))
    buffer = io.BytesIO()

    if content_type == "image/png":
        image.save(buffer, format="PNG", optimize=True)
    else:
        fmt = "JPEG" if content_type == "image/jpeg" else "WEBP"
        if fmt == "JPEG" and image.mode in ("RGBA", "P"):
            image = image.convert("RGB")  # JPEG no soporta canal alfa
        image.save(buffer, format=fmt, quality=80, optimize=True)

    return buffer.getvalue()


def _storage_path_from_url(property_id: str, stored_url: str) -> str:
    """Reconstruye el path interno de Storage (relativo al bucket) a partir
    de la URL firmada guardada en property_images.url. Evita depender de una
    columna 'path' que no existe en el esquema del Bloque 1 — si más
    adelante suman esa columna, esta función deja de hacer falta."""
    filename = stored_url.split("?")[0].rstrip("/").split("/")[-1]
    return f"{property_id}/{filename}"


def upload_property_image(property_id: str, file: UploadFile, current_count: int) -> dict:
    """Sube y comprime una foto de una propiedad a Supabase Storage.
    Devuelve {'url': str, 'order_index': int} listo para insertar en
    property_images desde property_service."""

    if current_count >= MAX_IMAGES_PER_PROPERTY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ya alcanzaste el máximo de {MAX_IMAGES_PER_PROPERTY} fotos por propiedad.",
        )

    content_type = file.content_type
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no permitido. Solo se aceptan imágenes JPG, PNG o WEBP.",
        )

    raw_bytes = file.file.read()
    if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La imagen supera el tamaño máximo permitido de 5MB.",
        )

    try:
        compressed_bytes = _compress_image(raw_bytes, content_type)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se pudo procesar la imagen. Verificá que el archivo no esté corrupto.",
        )

    extension = ALLOWED_CONTENT_TYPES[content_type]
    file_path = f"{property_id}/{uuid4()}.{extension}"

    admin = get_supabase_admin()

    try:
        admin.storage.from_(BUCKET_NAME).upload(
            file_path,
            compressed_bytes,
            {"content-type": content_type},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al subir la imagen. Intentá de nuevo.",
        )

    try:
        signed = admin.storage.from_(BUCKET_NAME).create_signed_url(
            file_path, SIGNED_URL_EXPIRES_IN
        )
        url = signed["signedURL"]
    except Exception:
        # El archivo se subió pero no pudimos generar el link — lo borramos
        # para no dejar un huérfano en Storage sin URL utilizable.
        admin.storage.from_(BUCKET_NAME).remove([file_path])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La imagen se subió pero no se pudo generar el enlace de acceso. Intentá de nuevo.",
        )

    return {"url": url, "order_index": current_count}


def delete_property_image(property_id: str, image_id: str) -> None:
    """Elimina una foto: primero del Storage, luego el registro en la BD."""
    admin = get_supabase_admin()

    record = (
        admin.table("property_images")
        .select("*")
        .eq("id", image_id)
        .eq("property_id", property_id)
        .single()
        .execute()
    )
    if not record.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La imagen no existe o no pertenece a esta propiedad.",
        )

    storage_path = _storage_path_from_url(property_id, record.data["url"])

    try:
        admin.storage.from_(BUCKET_NAME).remove([storage_path])
    except Exception:
        # Si el archivo ya no está en Storage (ej: borrado manual) no
        # bloqueamos el borrado del registro: preferible eso a dejar una
        # foto fantasma que el publicador no puede sacar de su propiedad.
        pass

    admin.table("property_images").delete().eq("id", image_id).execute()


def reorder_property_images(property_id: str, image_ids_in_order: list[str]) -> None:
    """Reasigna order_index (0-based) según el orden recibido del publicador."""
    admin = get_supabase_admin()

    existing = (
        admin.table("property_images")
        .select("id")
        .eq("property_id", property_id)
        .execute()
    )
    existing_ids = {row["id"] for row in (existing.data or [])}

    if set(image_ids_in_order) != existing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La lista de imágenes no coincide con las fotos actuales de la propiedad.",
        )

    for index, image_id in enumerate(image_ids_in_order):
        admin.table("property_images").update({"order_index": index}).eq(
            "id", image_id
        ).eq("property_id", property_id).execute()