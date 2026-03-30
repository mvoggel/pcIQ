"""
Supabase client — lazy singleton.

Usage:
    from app.db.client import get_db
    db = get_db()
    db.table("form_d_filings").upsert({...}).execute()
"""

from functools import lru_cache

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_db() -> Client:
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in .env before writing to the DB."
        )
    return create_client(settings.supabase_url, settings.supabase_anon_key)
