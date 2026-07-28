# Supabase Setup Guide — ValuNest

This guide walks you through connecting ValuNest to a Supabase cloud database.

---

## 1. Create a Supabase Project

1. Go to [supabase.com](https://supabase.com) and sign in (or create a free account).
2. Click **New Project**.
3. Choose an organization, give the project a name (e.g., `valunest`), set a database password, and select a region close to you.
4. Wait for the project to finish provisioning (~1 minute).

---

## 2. Get Your API Credentials

1. In the Supabase dashboard, go to **Project Settings → API**.
2. Copy two values:
   - **Project URL** — looks like `https://abcdefg.supabase.co`
   - **service_role key** (under "Project API keys") — a long JWT string starting with `eyJ...`

> ⚠️ **Use the `service_role` key** (not the `anon` key) for server-side access. The service_role key bypasses Row Level Security (RLS) so your Flask app can read/write all tables.

---

## 3. Create the Database Tables

1. In the Supabase dashboard, go to **SQL Editor**.
2. Click **New Query**.
3. Open the file [`db/schema.sql`](db/schema.sql) from this project.
4. Copy the entire contents and paste into the SQL Editor.
5. Click **Run** (or press `Ctrl+Enter`).
6. You should see "Success. No rows returned" — all tables are now created.

You can verify by going to **Table Editor** in the sidebar — you should see:
- `users`
- `password_history`
- `login_logs`
- `bookings`
- `messages`
- `app_settings`
- `password_resets`

---

## 4. Set Environment Variables

### Option A: Using a `.env` file (Recommended for local development)

1. Copy the template:
   ```powershell
   copy .env.example .env
   ```

2. Edit `.env` and fill in your values:
   ```env
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_KEY=your-service-role-key-here
   ```

### Option B: Using PowerShell environment variables

```powershell
$env:SUPABASE_URL="https://your-project-id.supabase.co"
$env:SUPABASE_KEY="your-service-role-key-here"
```

---

## 5. Install Dependencies

```powershell
pip install supabase python-dotenv
```

Or install all dependencies from the requirements file:

```powershell
pip install -r requirements.txt
```

---

## 6. Test the Connection

Run a quick test to verify the connection works:

```powershell
python -c "from db.supabase_client import check_connection; ok, msg = check_connection(); print(msg)"
```

Expected output:
```
✓ Supabase client connected to https://your-project-id.supabase.co
Supabase connected successfully to https://your-project-id.supabase.co
```

---

## 7. Run the App

```powershell
python app.py
```

The console will show:
```
✓ Supabase connected and initialized.
 * Running on http://127.0.0.1:5000
```

Open `http://127.0.0.1:5000` and register/log in — your data now lives in Supabase!

---

## Folder Structure

```
house-price-prediction/
├── db/
│   ├── __init__.py          # Package exports
│   ├── supabase_client.py   # Client singleton & connection check
│   ├── crud.py              # All CRUD operations
│   ├── models.py            # RowProxy compatibility wrapper
│   └── schema.sql           # SQL to create tables in Supabase
├── .env                     # Your credentials (git-ignored)
├── .env.example             # Template for .env
├── app.py                   # Flask application (uses db/ package)
├── requirements.txt         # Python dependencies
└── SUPABASE_SETUP.md        # This file
```

---

## Offline / Local Development

If `SUPABASE_URL` and `SUPABASE_KEY` are **not set**, the app automatically falls back to a local SQLite database (`users.db`). This is useful for:

- Working without internet
- Quick local testing
- CI/CD pipelines

No code changes are needed — just remove or comment out the variables in `.env`.

---

## Troubleshooting

| Issue | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'supabase'` | Run `pip install supabase` |
| `Supabase connection test failed` | Verify your URL and key are correct |
| `relation "users" does not exist` | Run `db/schema.sql` in the SQL Editor |
| `permission denied for table` | Use the `service_role` key, not the `anon` key |
| App uses SQLite instead of Supabase | Check that `.env` is in the project root and has both variables |
