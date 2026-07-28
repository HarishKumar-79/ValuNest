"""
db — ValuNest Database Package.

Provides a clean interface for all database operations.
Auto-selects between Supabase (cloud) and SQLite (local fallback).

Usage in app.py:
    from db import crud as db
    from db.crud import init_db

    init_db()
    user = db.get_user_by_email("test@gmail.com")
"""

from db.supabase_client import (
    get_supabase,
    is_supabase_configured,
    check_connection,
)
from db.crud import init_db

__all__ = [
    "get_supabase",
    "is_supabase_configured",
    "check_connection",
    "init_db",
]
