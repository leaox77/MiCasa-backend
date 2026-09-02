from app.core.supabase import get_supabase_admin


def register_view(property_id: str, user_id: str = None, session_id: str = None) -> None:
    """Registra una vista única. Si ya existe el registro, no hace nada
    (la constraint UNIQUE en la BD lo previene silenciosamente)."""
    if not user_id and not session_id:
        return  # Sin identificador no hay forma de deduplicar, ignorar

    admin = get_supabase_admin()

    # Verificar si ya existe la vista para no llamar a insert innecesariamente
    query = admin.table("property_views").select("id").eq("property_id", property_id)
    if user_id:
        query = query.eq("user_id", user_id)
    else:
        query = query.eq("session_id", session_id)

    existing = query.maybe_single().execute()
    if existing.data:
        return  # Vista ya registrada, no hacer nada

    data: dict = {"property_id": property_id}
    if user_id:
        data["user_id"] = user_id
    else:
        data["session_id"] = session_id

    try:
        admin.table("property_views").insert(data).execute()
        # El trigger trg_increment_view_count en la BD incrementa
        # properties.view_count automáticamente al insertar aquí
    except Exception:
        pass  # Si falla por constraint duplicada, ignorar silenciosamente