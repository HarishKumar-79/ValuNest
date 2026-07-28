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
            print("✓ Supabase connected and initialized.")
        except Exception as e:
            print(f"✗ Supabase initialization error: {e}")
    else:
        conn = _get_sqlite()
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, plain_password TEXT NOT NULL,
            phone TEXT DEFAULT '', address TEXT DEFAULT '',
            photo TEXT DEFAULT '', status TEXT DEFAULT 'active',
            google_sub TEXT DEFAULT '', oauth_provider TEXT DEFAULT '',
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
            emi_total_payable REAL DEFAULT 0, emi_next_date TEXT DEFAULT '')""")
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
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            ("emi_rate", "12"),
        )
        conn.commit()
        conn.close()
        print("✓ SQLite database initialized.")


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
            return _wrap(result.data[0]) if result.data else None
        except Exception as e:
            print(f"Error in create_booking: {e}")
            return None
    else:
        conn = _get_sqlite()
        conn.execute(
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
        conn.close()
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
