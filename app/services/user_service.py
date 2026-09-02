from fastapi import HTTPException, status
from app.core.supabase import get_supabase_admin
from app.schemas.users import ProfileUpdate


def get_profile(user_id: str) -> dict:
    """Devuelve el perfil completo del usuario autenticado."""
    admin = get_supabase_admin()
    result = admin.table("profiles").select("*").eq("id", user_id).single().execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil no encontrado.",
        )

    return result.data


def update_profile(user_id: str, data: ProfileUpdate) -> dict:
    """Actualiza los campos editables del perfil del usuario autenticado."""
    admin = get_supabase_admin()

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se enviaron campos para actualizar.",
        )

    result = admin.table("profiles").update(update_data).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Perfil no encontrado.",
        )

    return result.data[0]


def get_public_profile(publisher_id: str) -> dict:
    """Devuelve el perfil público de un publicador (sin datos sensibles)."""
    admin = get_supabase_admin()
    result = (
        admin.table("profiles")
        .select("*")
        .eq("id", publisher_id)
        .eq("role", "publisher")
        .single()
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publicador no encontrado.",
        )

    return result.data