from supabase import create_client, Client
from app.core.config import get_settings
from functools import lru_cache

settings = get_settings()


@lru_cache()
def get_supabase() -> Client:
    """Cliente estándar — usa anon key. Respeta RLS."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


@lru_cache()
def get_supabase_admin() -> Client:
    """Cliente admin — usa service role key. Bypasea RLS.
    Usar SOLO en operaciones administrativas del backend."""
    return create_client(
        settings.supabase_url, settings.supabase_service_role_key
    )