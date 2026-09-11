"""
CRUD Operations for ValuNest Database.

Every database interaction in the app goes through this module.
Each function auto-selects between Supabase (cloud) and SQLite (local fallback).
"""

import sqlite3
from datetime import datetime

from db.supabase_client import get_supabase, is_supabase_configured, SQLITE_DB_PATH
from db.models import RowProxy


# ════════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════════

def _get_sqlite():
    """Return a new SQLite connection with Row factory."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _sb():
    """Shorthand for get_supabase()."""
    return get_supabase()


def _wrap(row):
    """Wrap a Supabase dict result in RowProxy, or return None."""
    return RowProxy(row) if row else None


def _wrap_list(rows):
    """Wrap a list of Supabase dict results in RowProxy objects."""
    return [RowProxy(r) for r in (rows or [])]


# ════════════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ════════════════════════════════════════════════════════════════

def init_db():
    """Initialize database tables and insert default settings.

    - Supabase: tables must be created via SQL Editor (db/schema.sql).
      This only ensures default settings exist.
    - SQLite: creates all tables programmatically.
    """
    if is_supabase_configured():
        try:
            _sb().table("app_settings").upsert(
                {"key": "emi_rate", "value": "12"},
                on_conflict="key",
            ).execute()
            print("[OK] Supabase connected and initialized.")
            sync_all_confirmed_bookings_to_billing()
        except Exception as e:
            print(f"[ERROR] Supabase initialization error: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, plain_password TEXT NOT NULL,
            phone TEXT DEFAULT '', address TEXT DEFAULT '',
            photo TEXT DEFAULT '', status TEXT DEFAULT 'active',
            google_sub TEXT DEFAULT '', oauth_provider TEXT DEFAULT '',
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS password_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, plain_password TEXT NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS login_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, user_name TEXT NOT NULL,
            action TEXT NOT NULL,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, user_name TEXT NOT NULL,
            city TEXT NOT NULL, location TEXT NOT NULL,
            price REAL NOT NULL, payment_method TEXT,
            txn_id TEXT DEFAULT '', booking_type TEXT DEFAULT 'predicted',
            status TEXT DEFAULT 'cart', paid_at TIMESTAMP,
            booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payment_bank TEXT DEFAULT '', emi_tenure INTEGER DEFAULT 0,
            emi_rate REAL DEFAULT 0, emi_monthly REAL DEFAULT 0,
            emi_total_payable REAL DEFAULT 0, emi_next_date TEXT DEFAULT '',
            latitude REAL DEFAULT NULL, longitude REAL DEFAULT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL, sender_name TEXT NOT NULL,
            sender_email TEXT DEFAULT '', sender_role TEXT NOT NULL,
            receiver_id INTEGER, receiver_name TEXT DEFAULT '',
            receiver_email TEXT DEFAULT '', receiver_role TEXT NOT NULL,
            subject TEXT NOT NULL, body TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '')""")
        conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at REAL NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS billing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
            invoice_number TEXT NOT NULL UNIQUE,
            billing_name TEXT NOT NULL DEFAULT '',
            billing_email TEXT NOT NULL DEFAULT '',
            billing_phone TEXT DEFAULT '',
            billing_address TEXT DEFAULT '',
            subtotal REAL NOT NULL DEFAULT 0,
            tax_rate REAL NOT NULL DEFAULT 0,
            tax_amount REAL NOT NULL DEFAULT 0,
            discount REAL NOT NULL DEFAULT 0,
            total REAL NOT NULL DEFAULT 0,
            payment_method TEXT DEFAULT '',
            payment_status TEXT DEFAULT 'paid',
            notes TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS emi_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            billing_id INTEGER NOT NULL, booking_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL, installment_no INTEGER NOT NULL,
            due_date TEXT NOT NULL, amount_due REAL NOT NULL DEFAULT 0,
            amount_paid REAL NOT NULL DEFAULT 0, penalty REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'pending', paid_at TIMESTAMP,
            txn_id TEXT DEFAULT '', payment_method TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            ("emi_rate", "12"),
        )
        conn.commit()
        # Safe migration: add columns if missing (for existing databases)
        for col_sql in [
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'",
            "ALTER TABLE bookings ADD COLUMN latitude REAL DEFAULT NULL",
            "ALTER TABLE bookings ADD COLUMN longitude REAL DEFAULT NULL",
        ]:
            try:
                conn.execute(col_sql)
                conn.commit()
            except Exception:
                pass  # Column already exists
        conn.close()
        print("[OK] SQLite database initialized.")
        sync_all_confirmed_bookings_to_billing()


# ════════════════════════════════════════════════════════════════
# USERS — CRUD
# ════════════════════════════════════════════════════════════════

def create_user(name, email, hashed_password, plain_password,
                photo="", status="active", google_sub="", oauth_provider=""):
    """Insert a new user. Returns (row, None) or (None, error_string)."""
    data = {
        "name": name, "email": email,
        "password": hashed_password, "plain_password": plain_password,
        "photo": photo, "status": status,
        "google_sub": google_sub, "oauth_provider": oauth_provider,
    }
    if is_supabase_configured():
        try:
            result = _sb().table("users").insert(data).execute()
            if result.data:
                return _wrap(result.data[0]), None
            return None, "Failed to create user."
        except Exception as e:
            msg = str(e)
            if "duplicate" in msg.lower() or "unique" in msg.lower() or "23505" in msg:
                return None, "Email already registered."
            return None, f"Database error: {msg}"
    else:
        conn = _get_sqlite()
        try:
            conn.execute(
                "INSERT INTO users (name,email,password,plain_password,photo,status,google_sub,oauth_provider) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (name, email, hashed_password, plain_password, photo, status, google_sub, oauth_provider),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            conn.close()
            return row, None
        except sqlite3.IntegrityError:
            conn.close()
            return None, "Email already registered."


def get_user_by_id(user_id):
    """Fetch a single user by ID. Returns row or None."""
    if is_supabase_configured():
        try:
            result = _sb().table("users").select("*").eq("id", user_id).execute()
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_user_by_id: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        conn.close()
        return row


def get_user_by_email(email):
    """Fetch a single user by email. Returns row or None."""
    if is_supabase_configured():
        try:
            result = _sb().table("users").select("*").eq("email", email).execute()
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_user_by_email: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        return row


def get_all_users():
    """Return all users ordered by id DESC."""
    if is_supabase_configured():
        try:
            result = _sb().table("users").select("*").order("id", desc=True).execute()
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_all_users: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
        conn.close()
        return rows


def count_users():
    """Return total number of users."""
    if is_supabase_configured():
        try:
            result = _sb().table("users").select("id", count="exact").execute()
            return result.count or 0
        except Exception as e:
            print(f"Error in count_users: {e}")
            return 0
    else:
        conn = _get_sqlite()
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        return count


def update_user(user_id, **fields):
    """Update user fields. Pass only the columns you want to change."""
    if not fields:
        return
    if is_supabase_configured():
        try:
            _sb().table("users").update(fields).eq("id", user_id).execute()
        except Exception as e:
            print(f"Error in update_user: {e}")
    else:
        conn = _get_sqlite()
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [user_id]
        conn.execute(f"UPDATE users SET {sets} WHERE id=?", vals)
        conn.commit()
        conn.close()


def delete_user(user_id):
    """Delete a user and all their related data (bookings, logs, passwords)."""
    if is_supabase_configured():
        try:
            sb = _sb()
            sb.table("bookings").delete().eq("user_id", user_id).execute()
            sb.table("password_history").delete().eq("user_id", user_id).execute()
            sb.table("login_logs").delete().eq("user_id", user_id).execute()
            sb.table("messages").delete().eq("sender_id", user_id).execute()
            sb.table("password_resets").delete().eq("user_id", user_id).execute()
            sb.table("users").delete().eq("id", user_id).execute()
        except Exception as e:
            print(f"Error in delete_user: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("DELETE FROM bookings WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM password_history WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM login_logs WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()


def block_user(user_id):
    """Set a user's status to 'blocked'."""
    update_user(user_id, status="blocked")


def unblock_user(user_id):
    """Set a user's status to 'active'."""
    update_user(user_id, status="active")


def get_users_for_messaging():
    """Return id, name, email for all users (for admin message dropdown)."""
    if is_supabase_configured():
        try:
            result = _sb().table("users").select("id,name,email").order("name").execute()
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_users_for_messaging: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute("SELECT id, name, email FROM users ORDER BY name ASC").fetchall()
        conn.close()
        return rows


# ════════════════════════════════════════════════════════════════
# BOOKINGS — CRUD
# ════════════════════════════════════════════════════════════════

def create_booking(user_id, user_name, city, location, price,
                   booking_type="predicted", status="cart",
                   payment_method=None, txn_id="", paid_at=None,
                   payment_bank="", emi_tenure=None, emi_rate=None,
                   emi_monthly=None, emi_total_payable=None, emi_next_date=None):
    """Insert a new booking row."""
    data = {
        "user_id": user_id, "user_name": user_name,
        "city": city, "location": location, "price": price,
        "booking_type": booking_type, "status": status,
        "payment_method": payment_method, "txn_id": txn_id or "",
        "payment_bank": payment_bank or "",
        "emi_tenure": emi_tenure or 0, "emi_rate": emi_rate or 0,
        "emi_monthly": emi_monthly or 0, "emi_total_payable": emi_total_payable or 0,
        "emi_next_date": emi_next_date or "",
    }
    if paid_at:
        data["paid_at"] = paid_at

    if is_supabase_configured():
        try:
            result = _sb().table("bookings").insert(data).execute()
            created = _wrap(result.data[0]) if result.data else None
            if created and status == "confirmed":
                _ensure_billing_for_booking(created)
            return created
        except Exception as e:
            print(f"Error in create_booking: {e}")
            return None
    else:
        conn = _get_sqlite()
        cur = conn.execute(
            """INSERT INTO bookings
               (user_id,user_name,city,location,price,booking_type,status,
                payment_method,txn_id,paid_at,payment_bank,
                emi_tenure,emi_rate,emi_monthly,emi_total_payable,emi_next_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user_id, user_name, city, location, price, booking_type, status,
             payment_method, txn_id or "", paid_at,
             payment_bank or "", emi_tenure or 0, emi_rate or 0,
             emi_monthly or 0, emi_total_payable or 0, emi_next_date or ""),
        )
        conn.commit()
        last_id = cur.lastrowid
        conn.close()
        if status == "confirmed" and last_id:
            created = get_booking_by_id(last_id)
            if created:
                _ensure_billing_for_booking(created)
        return True


def get_booking_by_id(booking_id):
    """Fetch a single booking by ID."""
    if is_supabase_configured():
        try:
            result = _sb().table("bookings").select("*").eq("id", booking_id).execute()
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_booking_by_id: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        conn.close()
        return row


def get_booking_for_user(booking_id, user_id):
    """Fetch a booking that belongs to a specific user."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("*")
                      .eq("id", booking_id).eq("user_id", user_id).execute())
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_booking_for_user: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT * FROM bookings WHERE id=? AND user_id=?",
            (booking_id, user_id),
        ).fetchone()
        conn.close()
        return row


def get_user_cart_item(user_id, city, location):
    """Check if a user already has a cart item for a city/location."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("id")
                      .eq("user_id", user_id).eq("city", city)
                      .eq("location", location).eq("status", "cart").execute())
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_user_cart_item: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT id FROM bookings WHERE user_id=? AND city=? AND location=? AND status='cart'",
            (user_id, city, location),
        ).fetchone()
        conn.close()
        return row


def get_user_bookings_by_status(user_id, status):
    """Get all bookings for a user with a given status, ordered by date."""
    order_col = "paid_at" if status == "confirmed" else "booked_at"
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("*")
                      .eq("user_id", user_id).eq("status", status)
                      .order(order_col, desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_user_bookings_by_status: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            f"SELECT * FROM bookings WHERE user_id=? AND status=? ORDER BY {order_col} DESC",
            (user_id, status),
        ).fetchall()
        conn.close()
        return rows


def get_user_confirmed_bookings(user_id):
    """Get confirmed bookings for map display."""
    return get_user_bookings_by_status(user_id, "confirmed")


def get_taken_locations(city):
    """Get locations already booked (cart or confirmed) in a city."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("location")
                      .eq("city", city).in_("status", ["cart", "confirmed"]).execute())
            return [r["location"] for r in (result.data or [])]
        except Exception as e:
            print(f"Error in get_taken_locations: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT location FROM bookings WHERE city=? AND status IN ('cart','confirmed')",
            (city,),
        ).fetchall()
        conn.close()
        return [r["location"] for r in rows]


def get_all_bookings():
    """Return all bookings ordered by id DESC (admin view)."""
    if is_supabase_configured():
        try:
            result = _sb().table("bookings").select("*").order("id", desc=True).execute()
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_all_bookings: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
        conn.close()
        return rows


def update_booking(booking_id, **fields):
    """Update booking fields by ID."""
    if not fields:
        return
    if is_supabase_configured():
        try:
            _sb().table("bookings").update(fields).eq("id", booking_id).execute()
        except Exception as e:
            print(f"Error in update_booking: {e}")
    else:
        conn = _get_sqlite()
        sets = ", ".join(f"{k}=?" for k in fields)
        vals = list(fields.values()) + [booking_id]
        conn.execute(f"UPDATE bookings SET {sets} WHERE id=?", vals)
        conn.commit()
        conn.close()


def confirm_booking(booking_id, payment_method, txn_id, paid_at,
                    payment_bank="", emi_tenure=None, emi_rate=None,
                    emi_monthly=None, emi_total_payable=None, emi_next_date=None):
    """Mark a booking as confirmed with payment details."""
    update_booking(
        booking_id,
        payment_method=payment_method,
        txn_id=txn_id,
        status="confirmed",
        paid_at=paid_at,
        payment_bank=payment_bank or "",
        emi_tenure=emi_tenure or 0,
        emi_rate=emi_rate or 0,
        emi_monthly=emi_monthly or 0,
        emi_total_payable=emi_total_payable or 0,
        emi_next_date=emi_next_date or "",
    )
    b = get_booking_by_id(booking_id)
    if b:
        _ensure_billing_for_booking(b)


def delete_booking(booking_id):
    """Delete a booking by ID."""
    if is_supabase_configured():
        try:
            _sb().table("bookings").delete().eq("id", booking_id).execute()
        except Exception as e:
            print(f"Error in delete_booking: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
        conn.commit()
        conn.close()


def remove_cart_item(booking_id, user_id):
    """Remove a cart item for a specific user."""
    if is_supabase_configured():
        try:
            (_sb().table("bookings").delete()
             .eq("id", booking_id).eq("user_id", user_id)
             .eq("status", "cart").execute())
        except Exception as e:
            print(f"Error in remove_cart_item: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            "DELETE FROM bookings WHERE id=? AND user_id=? AND status='cart'",
            (booking_id, user_id),
        )
        conn.commit()
        conn.close()


# ════════════════════════════════════════════════════════════════
# LOGIN LOGS
# ════════════════════════════════════════════════════════════════

def create_login_log(user_id, user_name, action):
    """Record a login or logout event."""
    if is_supabase_configured():
        try:
            _sb().table("login_logs").insert({
                "user_id": user_id, "user_name": user_name, "action": action,
            }).execute()
        except Exception as e:
            print(f"Error in create_login_log: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            "INSERT INTO login_logs (user_id,user_name,action) VALUES (?,?,?)",
            (user_id, user_name, action),
        )
        conn.commit()
        conn.close()


def get_recent_login_logs(limit=10):
    """Get the most recent login logs."""
    if is_supabase_configured():
        try:
            result = (_sb().table("login_logs").select("*")
                      .order("logged_at", desc=True).limit(limit).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_recent_login_logs: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM login_logs ORDER BY logged_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return rows


def get_older_login_logs(offset=10):
    """Get login logs beyond the most recent 'offset' rows."""
    if is_supabase_configured():
        try:
            result = (_sb().table("login_logs").select("*")
                      .order("logged_at", desc=True)
                      .range(offset, offset + 999).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_older_login_logs: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM login_logs ORDER BY logged_at DESC LIMIT -1 OFFSET ?", (offset,)
        ).fetchall()
        conn.close()
        return rows


def get_user_login_logs(user_id):
    """Get all login logs for a specific user."""
    if is_supabase_configured():
        try:
            result = (_sb().table("login_logs").select("*")
                      .eq("user_id", user_id)
                      .order("logged_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_user_login_logs: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM login_logs WHERE user_id=? ORDER BY logged_at DESC",
            (user_id,),
        ).fetchall()
        conn.close()
        return rows


def count_user_actions(user_id, action):
    """Count how many times a user performed an action (login/logout)."""
    if is_supabase_configured():
        try:
            result = (_sb().table("login_logs").select("id", count="exact")
                      .eq("user_id", user_id).eq("action", action).execute())
            return result.count or 0
        except Exception as e:
            print(f"Error in count_user_actions: {e}")
            return 0
    else:
        conn = _get_sqlite()
        count = conn.execute(
            "SELECT COUNT(*) FROM login_logs WHERE user_id=? AND action=?",
            (user_id, action),
        ).fetchone()[0]
        conn.close()
        return count


# ════════════════════════════════════════════════════════════════
# PASSWORD HISTORY
# ════════════════════════════════════════════════════════════════

def add_password_history(user_id, plain_password):
    """Record a password change in history."""
    if is_supabase_configured():
        try:
            _sb().table("password_history").insert({
                "user_id": user_id, "plain_password": plain_password,
            }).execute()
        except Exception as e:
            print(f"Error in add_password_history: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            "INSERT INTO password_history (user_id,plain_password) VALUES (?,?)",
            (user_id, plain_password),
        )
        conn.commit()
        conn.close()


def get_password_history(user_id):
    """Get password change history for a user (newest first)."""
    if is_supabase_configured():
        try:
            result = (_sb().table("password_history").select("*")
                      .eq("user_id", user_id)
                      .order("changed_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_password_history: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM password_history WHERE user_id=? ORDER BY changed_at DESC",
            (user_id,),
        ).fetchall()
        conn.close()
        return rows


# ════════════════════════════════════════════════════════════════
# PASSWORD RESETS
# ════════════════════════════════════════════════════════════════

def create_reset_token(user_id, token, expires_at):
    """Store a password-reset token."""
    if is_supabase_configured():
        try:
            _sb().table("password_resets").insert({
                "user_id": user_id, "token": token, "expires_at": expires_at,
            }).execute()
        except Exception as e:
            print(f"Error in create_reset_token: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            "INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at),
        )
        conn.commit()
        conn.close()


def get_valid_reset(token, current_time):
    """Fetch a valid (unused, non-expired) password-reset request."""
    if is_supabase_configured():
        try:
            result = (_sb().table("password_resets").select("*")
                      .eq("token", token).eq("used", 0)
                      .gt("expires_at", current_time).execute())
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_valid_reset: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT * FROM password_resets WHERE token=? AND used=0 AND expires_at > ?",
            (token, current_time),
        ).fetchone()
        conn.close()
        return row


def mark_reset_used(reset_id):
    """Mark a password-reset token as used."""
    if is_supabase_configured():
        try:
            _sb().table("password_resets").update({"used": 1}).eq("id", reset_id).execute()
        except Exception as e:
            print(f"Error in mark_reset_used: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("UPDATE password_resets SET used=1 WHERE id=?", (reset_id,))
        conn.commit()
        conn.close()


# ════════════════════════════════════════════════════════════════
# MESSAGES
# ════════════════════════════════════════════════════════════════

def send_message(sender_id, sender_name, sender_email, sender_role,
                 receiver_id, receiver_name, receiver_email, receiver_role,
                 subject, body):
    """Insert a new message."""
    data = {
        "sender_id": sender_id, "sender_name": sender_name,
        "sender_email": sender_email, "sender_role": sender_role,
        "receiver_id": receiver_id, "receiver_name": receiver_name,
        "receiver_email": receiver_email, "receiver_role": receiver_role,
        "subject": subject, "body": body,
    }
    if is_supabase_configured():
        try:
            _sb().table("messages").insert(data).execute()
        except Exception as e:
            print(f"Error in send_message: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            """INSERT INTO messages
               (sender_id,sender_name,sender_email,sender_role,
                receiver_id,receiver_name,receiver_email,receiver_role,subject,body)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (sender_id, sender_name, sender_email, sender_role,
             receiver_id, receiver_name, receiver_email, receiver_role,
             subject, body),
        )
        conn.commit()
        conn.close()


def get_all_messages():
    """Return all messages ordered by created_at DESC (admin inbox)."""
    if is_supabase_configured():
        try:
            result = (_sb().table("messages").select("*")
                      .order("created_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_all_messages: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute("SELECT * FROM messages ORDER BY created_at DESC").fetchall()
        conn.close()
        return rows


def get_user_messages(user_id):
    """Return messages visible to a specific user."""
    if is_supabase_configured():
        try:
            result = (_sb().table("messages").select("*")
                      .or_(f"sender_id.eq.{user_id},receiver_id.eq.{user_id},receiver_role.eq.admin")
                      .order("created_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_user_messages: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM messages WHERE sender_id=? OR receiver_id=? OR receiver_role='admin' "
            "ORDER BY created_at DESC",
            (user_id, user_id),
        ).fetchall()
        conn.close()
        return rows


# ════════════════════════════════════════════════════════════════
# APP SETTINGS
# ════════════════════════════════════════════════════════════════

def get_setting(key, default_value=""):
    """Read a setting value by key."""
    if is_supabase_configured():
        try:
            result = _sb().table("app_settings").select("value").eq("key", key).execute()
            if result.data:
                return result.data[0]["value"]
            return default_value
        except Exception as e:
            print(f"Error in get_setting: {e}")
            return default_value
    else:
        conn = _get_sqlite()
        row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row["value"] if row else default_value


def set_setting(key, value):
    """Upsert a setting value."""
    if is_supabase_configured():
        try:
            _sb().table("app_settings").upsert(
                {"key": key, "value": str(value)}, on_conflict="key",
            ).execute()
        except Exception as e:
            print(f"Error in set_setting: {e}")
    else:
        conn = _get_sqlite()
        conn.execute(
            """INSERT INTO app_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (key, str(value)),
        )
        conn.commit()
        conn.close()


# ════════════════════════════════════════════════════════════════
# ROLE-BASED ACCESS
# ════════════════════════════════════════════════════════════════

def get_user_role(user_id):
    """Get the role of a user. Returns 'user' if not found."""
    user = get_user_by_id(user_id)
    if user:
        return user.get("role", "user") or "user"
    return "user"


def set_user_role(user_id, role):
    """Set the role of a user (admin/staff/user)."""
    if role not in ("admin", "staff", "user"):
        return
    update_user(user_id, role=role)


def get_users_by_role(role):
    """Get all users with a given role."""
    if is_supabase_configured():
        try:
            result = (_sb().table("users").select("*")
                      .eq("role", role).order("id", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_users_by_role: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM users WHERE role=? ORDER BY id DESC", (role,)
        ).fetchall()
        conn.close()
        return rows


# ════════════════════════════════════════════════════════════════
# ANALYTICS QUERIES
# ════════════════════════════════════════════════════════════════

def get_monthly_registrations(limit=12):
    """Return monthly user registration counts for the last N months.
    Returns list of dicts: [{"month": "2026-01", "count": 5}, ...]
    """
    if is_supabase_configured():
        try:
            # Supabase: use RPC or raw query via PostgREST isn't ideal;
            # fetch all users and aggregate in Python
            result = _sb().table("users").select("created_at").execute()
            return _aggregate_monthly(result.data, "created_at", limit)
        except Exception as e:
            print(f"Error in get_monthly_registrations: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count "
            "FROM users GROUP BY month ORDER BY month DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{"month": r["month"], "count": r["count"]} for r in rows]


def get_monthly_bookings(limit=12):
    """Return monthly confirmed booking counts."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("booked_at")
                      .eq("status", "confirmed").execute())
            return _aggregate_monthly(result.data, "booked_at", limit)
        except Exception as e:
            print(f"Error in get_monthly_bookings: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT strftime('%Y-%m', booked_at) as month, COUNT(*) as count "
            "FROM bookings WHERE status='confirmed' GROUP BY month ORDER BY month DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"month": r["month"], "count": r["count"]} for r in rows]


def get_revenue_by_month(limit=12):
    """Return monthly revenue totals."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("booked_at,price")
                      .eq("status", "confirmed").execute())
            return _aggregate_monthly_sum(result.data, "booked_at", "price", limit)
        except Exception as e:
            print(f"Error in get_revenue_by_month: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT strftime('%Y-%m', booked_at) as month, SUM(price) as total "
            "FROM bookings WHERE status='confirmed' GROUP BY month ORDER BY month DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [{"month": r["month"], "total": r["total"] or 0} for r in rows]


def get_top_cities(limit=10):
    """Return top cities by confirmed booking count."""
    if is_supabase_configured():
        try:
            result = (_sb().table("bookings").select("city")
                      .eq("status", "confirmed").execute())
            from collections import Counter
            counts = Counter(r["city"] for r in (result.data or []))
            top = counts.most_common(limit)
            return [{"city": c, "count": n} for c, n in top]
        except Exception as e:
            print(f"Error in get_top_cities: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT city, COUNT(*) as count FROM bookings WHERE status='confirmed' "
            "GROUP BY city ORDER BY count DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{"city": r["city"], "count": r["count"]} for r in rows]


def get_booking_status_distribution():
    """Return booking counts grouped by status."""
    if is_supabase_configured():
        try:
            result = _sb().table("bookings").select("status").execute()
            from collections import Counter
            counts = Counter(r["status"] for r in (result.data or []))
            return [{"status": s, "count": c} for s, c in counts.items()]
        except Exception as e:
            print(f"Error in get_booking_status_distribution: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM bookings GROUP BY status"
        ).fetchall()
        conn.close()
        return [{"status": r["status"], "count": r["count"]} for r in rows]


def get_todays_bookings_count():
    """Count bookings made today."""
    if is_supabase_configured():
        try:
            from datetime import date
            today = date.today().isoformat()
            result = (_sb().table("bookings").select("id", count="exact")
                      .gte("booked_at", today).execute())
            return result.count or 0
        except Exception as e:
            print(f"Error in get_todays_bookings_count: {e}")
            return 0
    else:
        conn = _get_sqlite()
        count = conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE date(booked_at) = date('now')"
        ).fetchone()[0]
        conn.close()
        return count


def count_unread_messages():
    """Count unread messages (for admin badge)."""
    if is_supabase_configured():
        try:
            result = (_sb().table("messages").select("id", count="exact")
                      .eq("is_read", 0).eq("receiver_role", "admin").execute())
            return result.count or 0
        except Exception as e:
            print(f"Error in count_unread_messages: {e}")
            return 0
    else:
        conn = _get_sqlite()
        count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE is_read=0 AND receiver_role='admin'"
        ).fetchone()[0]
        conn.close()
        return count


# ── Aggregation helpers (for Supabase where we fetch raw rows) ──

def _aggregate_monthly(rows, date_field, limit=12):
    """Aggregate rows by month from a date field."""
    from collections import Counter
    months = Counter()
    for r in (rows or []):
        val = r.get(date_field) or ""
        if len(val) >= 7:
            months[val[:7]] += 1
    sorted_months = sorted(months.items(), reverse=True)[:limit]
    return [{"month": m, "count": c} for m, c in sorted_months]


def _aggregate_monthly_sum(rows, date_field, value_field, limit=12):
    """Aggregate sum of a value field by month."""
    from collections import defaultdict
    months = defaultdict(float)
    for r in (rows or []):
        val = r.get(date_field) or ""
        if len(val) >= 7:
            months[val[:7]] += float(r.get(value_field) or 0)
    sorted_months = sorted(months.items(), reverse=True)[:limit]
    return [{"month": m, "total": t} for m, t in sorted_months]


# ════════════════════════════════════════════════════════════════
# BILLING — Invoice Records
# ════════════════════════════════════════════════════════════════

def _generate_invoice_number():
    """Generate a unique invoice number like VN-20260910-XXXX."""
    import uuid
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    short_id = uuid.uuid4().hex[:6].upper()
    return f"VN-{today}-{short_id}"


def create_billing(booking_id, user_id, billing_name, billing_email,
                   subtotal, total, payment_method="",
                   billing_phone="", billing_address="",
                   tax_rate=0, tax_amount=0, discount=0,
                   payment_status="paid", notes=""):
    """Create a billing/invoice record for a confirmed booking.

    Returns the created billing row (dict) or None on error.
    """
    invoice_number = _generate_invoice_number()
    if is_supabase_configured():
        try:
            result = _sb().table("billing").insert({
                "booking_id": booking_id,
                "user_id": user_id,
                "invoice_number": invoice_number,
                "billing_name": billing_name,
                "billing_email": billing_email,
                "billing_phone": billing_phone or "",
                "billing_address": billing_address or "",
                "subtotal": subtotal,
                "tax_rate": tax_rate or 0,
                "tax_amount": tax_amount or 0,
                "discount": discount or 0,
                "total": total,
                "payment_method": payment_method or "",
                "payment_status": payment_status or "paid",
                "notes": notes or "",
            }).execute()
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in create_billing: {e}")
            return None
    else:
        conn = _get_sqlite()
        cur = conn.execute(
            """INSERT INTO billing
            (booking_id, user_id, invoice_number, billing_name,
             billing_email, billing_phone, billing_address,
             subtotal, tax_rate, tax_amount, discount, total,
             payment_method, payment_status, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (booking_id, user_id, invoice_number, billing_name,
             billing_email, billing_phone or "", billing_address or "",
             subtotal, tax_rate or 0, tax_amount or 0, discount or 0,
             total, payment_method or "", payment_status or "paid",
             notes or ""),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM billing WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        conn.close()
        return _wrap(row)


def get_billing_by_id(billing_id):
    """Get a single billing record by ID."""
    if is_supabase_configured():
        try:
            result = (_sb().table("billing").select("*")
                      .eq("id", billing_id).limit(1).execute())
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_billing_by_id: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT * FROM billing WHERE id=?", (billing_id,)
        ).fetchone()
        conn.close()
        return _wrap(row)


def get_billing_by_invoice(invoice_number):
    """Get a billing record by invoice number."""
    if is_supabase_configured():
        try:
            result = (_sb().table("billing").select("*")
                      .eq("invoice_number", invoice_number)
                      .limit(1).execute())
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in get_billing_by_invoice: {e}")
            return None
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT * FROM billing WHERE invoice_number=?",
            (invoice_number,),
        ).fetchone()
        conn.close()
        return _wrap(row)


def get_billing_by_booking(booking_id):
    """Get billing record(s) for a specific booking."""
    if is_supabase_configured():
        try:
            result = (_sb().table("billing").select("*")
                      .eq("booking_id", booking_id)
                      .order("created_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_billing_by_booking: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM billing WHERE booking_id=? ORDER BY created_at DESC",
            (booking_id,),
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def get_user_billing(user_id):
    """Get all billing records for a user."""
    if is_supabase_configured():
        try:
            result = (_sb().table("billing").select("*")
                      .eq("user_id", user_id)
                      .order("created_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_user_billing: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM billing WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def get_all_billing():
    """Get all billing records (admin)."""
    if is_supabase_configured():
        try:
            result = (_sb().table("billing").select("*")
                      .order("created_at", desc=True).execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_all_billing: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM billing ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def update_billing(billing_id, **fields):
    """Update a billing record."""
    if not fields:
        return
    if is_supabase_configured():
        try:
            _sb().table("billing").update(fields).eq("id", billing_id).execute()
        except Exception as e:
            print(f"Error in update_billing: {e}")
    else:
        conn = _get_sqlite()
        parts = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE billing SET {parts} WHERE id=?",
            (*fields.values(), billing_id),
        )
        conn.commit()
        conn.close()


def delete_billing(billing_id):
    """Delete a billing record by ID."""
    if is_supabase_configured():
        try:
            _sb().table("billing").delete().eq("id", billing_id).execute()
        except Exception as e:
            print(f"Error in delete_billing: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("DELETE FROM billing WHERE id=?", (billing_id,))
        conn.commit()
        conn.close()


# ════════════════════════════════════════════════════════════════
# EMI PAYMENTS — Installment Tracking
# ════════════════════════════════════════════════════════════════

def create_emi_schedule(billing_id, booking_id, user_id,
                        tenure, monthly_amount, start_date=None):
    """Create the full EMI schedule (one row per installment).

    Args:
        billing_id: the parent billing record
        booking_id: the associated booking
        user_id: the buyer
        tenure: number of monthly installments
        monthly_amount: amount due each month
        start_date: first due date (defaults to next month)

    Returns a list of created emi_payment rows.
    """
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta

    if start_date is None:
        start_date = date.today() + relativedelta(months=1)
    elif isinstance(start_date, str):
        start_date = date.fromisoformat(start_date)

    rows_created = []
    for i in range(1, tenure + 1):
        due = start_date + relativedelta(months=i - 1)
        row = create_emi_payment(
            billing_id=billing_id,
            booking_id=booking_id,
            user_id=user_id,
            installment_no=i,
            due_date=due.isoformat(),
            amount_due=monthly_amount,
        )
        if row:
            rows_created.append(row)
    return rows_created


def create_emi_payment(billing_id, booking_id, user_id,
                       installment_no, due_date, amount_due,
                       amount_paid=0, status="pending"):
    """Create a single EMI installment record."""
    if is_supabase_configured():
        try:
            result = _sb().table("emi_payments").insert({
                "billing_id": billing_id,
                "booking_id": booking_id,
                "user_id": user_id,
                "installment_no": installment_no,
                "due_date": due_date,
                "amount_due": amount_due,
                "amount_paid": amount_paid or 0,
                "status": status or "pending",
            }).execute()
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in create_emi_payment: {e}")
            return None
    else:
        conn = _get_sqlite()
        cur = conn.execute(
            """INSERT INTO emi_payments
            (billing_id, booking_id, user_id, installment_no,
             due_date, amount_due, amount_paid, status)
            VALUES (?,?,?,?,?,?,?,?)""",
            (billing_id, booking_id, user_id, installment_no,
             due_date, amount_due, amount_paid or 0,
             status or "pending"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM emi_payments WHERE id=?", (cur.lastrowid,)
        ).fetchone()
        conn.close()
        return _wrap(row)


def get_emi_payments_by_billing(billing_id):
    """Get all installments for a billing record, ordered by installment_no."""
    if is_supabase_configured():
        try:
            result = (_sb().table("emi_payments").select("*")
                      .eq("billing_id", billing_id)
                      .order("installment_no").execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_emi_payments_by_billing: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM emi_payments WHERE billing_id=? ORDER BY installment_no",
            (billing_id,),
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def get_emi_payments_by_booking(booking_id):
    """Get all EMI installments for a booking."""
    if is_supabase_configured():
        try:
            result = (_sb().table("emi_payments").select("*")
                      .eq("booking_id", booking_id)
                      .order("installment_no").execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_emi_payments_by_booking: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM emi_payments WHERE booking_id=? ORDER BY installment_no",
            (booking_id,),
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def get_user_emi_payments(user_id, status=None):
    """Get all EMI installments for a user, optionally filtered by status."""
    if is_supabase_configured():
        try:
            q = _sb().table("emi_payments").select("*").eq("user_id", user_id)
            if status:
                q = q.eq("status", status)
            result = q.order("due_date").execute()
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_user_emi_payments: {e}")
            return []
    else:
        conn = _get_sqlite()
        sql = "SELECT * FROM emi_payments WHERE user_id=?"
        params = [user_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY due_date"
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return _wrap_list(rows)


def get_overdue_emi_payments():
    """Get all EMI installments that are overdue (past due_date and still pending)."""
    from datetime import date
    today = date.today().isoformat()
    if is_supabase_configured():
        try:
            result = (_sb().table("emi_payments").select("*")
                      .eq("status", "pending")
                      .lt("due_date", today)
                      .order("due_date").execute())
            return _wrap_list(result.data)
        except Exception as e:
            print(f"Error in get_overdue_emi_payments: {e}")
            return []
    else:
        conn = _get_sqlite()
        rows = conn.execute(
            "SELECT * FROM emi_payments WHERE status='pending' AND due_date < ? ORDER BY due_date",
            (today,),
        ).fetchall()
        conn.close()
        return _wrap_list(rows)


def mark_emi_paid(emi_id, txn_id="", payment_method="", penalty=0):
    """Mark an EMI installment as paid."""
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    if is_supabase_configured():
        try:
            # First get the record to know amount_due
            result = (_sb().table("emi_payments").select("amount_due")
                      .eq("id", emi_id).limit(1).execute())
            amount_due = result.data[0]["amount_due"] if result.data else 0
            _sb().table("emi_payments").update({
                "status": "paid",
                "amount_paid": amount_due,
                "paid_at": now,
                "txn_id": txn_id or "",
                "payment_method": payment_method or "",
                "penalty": penalty or 0,
            }).eq("id", emi_id).execute()
        except Exception as e:
            print(f"Error in mark_emi_paid: {e}")
    else:
        conn = _get_sqlite()
        row = conn.execute(
            "SELECT amount_due FROM emi_payments WHERE id=?", (emi_id,)
        ).fetchone()
        amount_due = row[0] if row else 0
        conn.execute(
            """UPDATE emi_payments
            SET status='paid', amount_paid=?, paid_at=?,
                txn_id=?, payment_method=?, penalty=?
            WHERE id=?""",
            (amount_due, now, txn_id or "",
             payment_method or "", penalty or 0, emi_id),
        )
        conn.commit()
        conn.close()


def update_emi_payment(emi_id, **fields):
    """Update an EMI payment record."""
    if not fields:
        return
    if is_supabase_configured():
        try:
            _sb().table("emi_payments").update(fields).eq("id", emi_id).execute()
        except Exception as e:
            print(f"Error in update_emi_payment: {e}")
    else:
        conn = _get_sqlite()
        parts = ", ".join(f"{k}=?" for k in fields)
        conn.execute(
            f"UPDATE emi_payments SET {parts} WHERE id=?",
            (*fields.values(), emi_id),
        )
        conn.commit()
        conn.close()


def delete_emi_payment(emi_id):
    """Delete an EMI payment record."""
    if is_supabase_configured():
        try:
            _sb().table("emi_payments").delete().eq("id", emi_id).execute()
        except Exception as e:
            print(f"Error in delete_emi_payment: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("DELETE FROM emi_payments WHERE id=?", (emi_id,))
        conn.commit()
        conn.close()


def _ensure_billing_for_booking(booking):
    """Ensure a billing entry (and optional EMI schedule) exists for a confirmed booking."""
    if not booking:
        return None

    status = booking["status"] if (isinstance(booking, dict) or hasattr(booking, "__getitem__")) else getattr(booking, "status", None)
    if status != "confirmed":
        return None

    booking_id = booking["id"]
    existing = get_billing_by_booking(booking_id)
    if existing:
        return existing[0] if isinstance(existing, list) and existing else existing

    user_id = booking["user_id"]
    user = get_user_by_id(user_id)

    billing_email = (user["email"] if user and "email" in user else "") or ""
    billing_phone = (user["phone"] if user and "phone" in user else "") or ""
    billing_address = (user["address"] if user and "address" in user else "") or ""
    user_name = booking["user_name"] if "user_name" in booking else "Customer"

    price = float(booking["price"] or 0)
    payment_method = booking["payment_method"] if (isinstance(booking, dict) or hasattr(booking, "__getitem__")) else getattr(booking, "payment_method", "Online")
    payment_method = payment_method or "Online"

    billing = create_billing(
        booking_id=booking_id,
        user_id=user_id,
        billing_name=user_name,
        billing_email=billing_email,
        billing_phone=billing_phone,
        billing_address=billing_address,
        subtotal=price,
        total=price,
        payment_method=payment_method,
        payment_status="paid",
        notes=f"Booking for {booking.get('location', '') if isinstance(booking, dict) else getattr(booking, 'location', '')}, {booking.get('city', '') if isinstance(booking, dict) else getattr(booking, 'city', '')}"
    )

    emi_tenure = booking["emi_tenure"] if (isinstance(booking, dict) or hasattr(booking, "__getitem__")) else getattr(booking, "emi_tenure", 0)
    emi_monthly = booking["emi_monthly"] if (isinstance(booking, dict) or hasattr(booking, "__getitem__")) else getattr(booking, "emi_monthly", 0)

    if payment_method == "EMI" and emi_tenure and billing:
        tenure = int(emi_tenure or 0)
        monthly_amount = float(emi_monthly or 0)
        if tenure > 0 and monthly_amount > 0:
            create_emi_schedule(
                billing_id=billing["id"],
                booking_id=booking_id,
                user_id=user_id,
                tenure=tenure,
                monthly_amount=monthly_amount
            )

    return billing


def sync_all_confirmed_bookings_to_billing():
    """Sync any existing confirmed bookings into billing table."""
    try:
        confirmed = get_all_bookings()
        for b in (confirmed or []):
            st = b["status"] if (isinstance(b, dict) or hasattr(b, "__getitem__")) else getattr(b, "status", None)
            if st == "confirmed":
                _ensure_billing_for_booking(b)
    except Exception as e:
        print(f"Error in sync_all_confirmed_bookings_to_billing: {e}")

