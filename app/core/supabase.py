from types import SimpleNamespace

from postgrest.exceptions import APIError
from postgrest._sync.request_builder import SyncMaybeSingleRequestBuilder, SyncSingleRequestBuilder
from supabase import create_client, Client
from app.core.config import get_settings
from functools import lru_cache

settings = get_settings()


def _maybe_single_execute(self):
    """postgrest-py 0.16 traga los errores reales de maybe_single() y lanza un
    APIError 204 confuso. Acá: 0 filas -> data=None; cualquier otro error se propaga."""
    try:
        return SyncSingleRequestBuilder.execute(self)
    except APIError as e:
        if e.details and "The result contains 0 rows" in e.details:
            return SimpleNamespace(data=None, count=None)
        raise


SyncMaybeSingleRequestBuilder.execute = _maybe_single_execute


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