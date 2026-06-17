from functools import lru_cache
from supabase import create_client, Client
from app.core.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """
    Returns a singleton Supabase client authenticated with the
    service_role key. This key bypasses Row Level Security, which is
    intentional: FastAPI is the trusted server-side intermediary, and
    every request is already authenticated via Firebase before it
    reaches this client.

    NEVER expose supabase_service_role_key to the Flutter app.
    """
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
