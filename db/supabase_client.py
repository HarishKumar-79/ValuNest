"""
Supabase Client — Singleton connection to Supabase.

Loads SUPABASE_URL and SUPABASE_KEY from environment variables (or .env file).
Falls back to local SQLite when credentials are not configured.
"""

import os
from dotenv import load_dotenv

# Load .env file from project root
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

# ── Configuration ──────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
SQLITE_DB_PATH = os.path.join(_BASE_DIR, "users.db")

# ── Singleton client ──────────────────────────────────────────
_supabase_client = None


def is_supabase_configured():
    """Return True when both SUPABASE_URL and SUPABASE_KEY are set."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def get_supabase():
    """Return the Supabase client singleton.

    Creates the client on first call and reuses it afterwards.
    Returns None if Supabase is not configured.
    """
    global _supabase_client

    if not is_supabase_configured():
        return None

    if _supabase_client is None:
        try:
            from supabase import create_client
            _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
            print(f"✓ Supabase client connected to {SUPABASE_URL}")
        except ImportError:
            print("✗ 'supabase' package not installed. Run: pip install supabase")
            return None
        except Exception as exc:
            print(f"✗ Supabase connection failed: {exc}")
            return None

    return _supabase_client


def check_connection():
    """Verify the Supabase connection is working.

    Returns (True, message) on success or (False, message) on failure.
    """
    if not is_supabase_configured():
        return True, "Using local SQLite database (Supabase not configured)."

    client = get_supabase()
    if client is None:
        return False, "Supabase client could not be created."

    try:
        # A lightweight query to test connectivity
        client.table("app_settings").select("key").limit(1).execute()
        return True, f"Supabase connected successfully to {SUPABASE_URL}"
    except Exception as exc:
        return False, f"Supabase connection test failed: {exc}"
