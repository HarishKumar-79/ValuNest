-- ============================================================
-- ValuNest — Supabase Database Schema
-- ============================================================
-- Run this ONCE in the Supabase SQL Editor (Dashboard → SQL Editor)
-- to create all required tables before starting the app.
-- ============================================================

-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id            BIGSERIAL PRIMARY KEY,
    name          VARCHAR NOT NULL,
    email         VARCHAR UNIQUE NOT NULL,
    password      VARCHAR NOT NULL,
    plain_password VARCHAR NOT NULL DEFAULT '',
    phone         VARCHAR DEFAULT '',
    address       VARCHAR DEFAULT '',
    photo         VARCHAR DEFAULT '',
    status        VARCHAR DEFAULT 'active',
    google_sub    VARCHAR DEFAULT '',
    oauth_provider VARCHAR DEFAULT '',
    role          VARCHAR DEFAULT 'user',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_status ON users (status);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- 2. PASSWORD HISTORY
CREATE TABLE IF NOT EXISTS password_history (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plain_password VARCHAR NOT NULL,
    changed_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pw_history_user ON password_history (user_id);

-- 3. LOGIN LOGS
CREATE TABLE IF NOT EXISTS login_logs (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL,
    user_name  VARCHAR NOT NULL,
    action     VARCHAR NOT NULL,
    logged_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_logs_user ON login_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_login_logs_time ON login_logs (logged_at DESC);

-- 4. BOOKINGS
CREATE TABLE IF NOT EXISTS bookings (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL,
    user_name        VARCHAR NOT NULL,
    city             VARCHAR NOT NULL,
    location         VARCHAR NOT NULL,
    price            DOUBLE PRECISION NOT NULL,
    payment_method   VARCHAR,
    txn_id           VARCHAR DEFAULT '',
    booking_type     VARCHAR DEFAULT 'predicted',
    status           VARCHAR DEFAULT 'cart',
    paid_at          TIMESTAMPTZ,
    booked_at        TIMESTAMPTZ DEFAULT NOW(),
    payment_bank     VARCHAR DEFAULT '',
    emi_tenure       INTEGER DEFAULT 0,
    emi_rate         DOUBLE PRECISION DEFAULT 0,
    emi_monthly      DOUBLE PRECISION DEFAULT 0,
    emi_total_payable DOUBLE PRECISION DEFAULT 0,
    emi_next_date    VARCHAR DEFAULT '',
    latitude         DOUBLE PRECISION DEFAULT NULL,
    longitude        DOUBLE PRECISION DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status);
CREATE INDEX IF NOT EXISTS idx_bookings_city ON bookings (city);

-- 5. MESSAGES
CREATE TABLE IF NOT EXISTS messages (
    id             BIGSERIAL PRIMARY KEY,
    sender_id      BIGINT NOT NULL,
    sender_name    VARCHAR NOT NULL,
    sender_email   VARCHAR DEFAULT '',
    sender_role    VARCHAR NOT NULL,
    receiver_id    BIGINT,
    receiver_name  VARCHAR DEFAULT '',
    receiver_email VARCHAR DEFAULT '',
    receiver_role  VARCHAR NOT NULL,
    subject        VARCHAR NOT NULL,
    body           TEXT NOT NULL,
    is_read        INTEGER DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages (sender_id);
CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages (receiver_id);

-- 6. APP SETTINGS
CREATE TABLE IF NOT EXISTS app_settings (
    key   VARCHAR PRIMARY KEY,
    value VARCHAR NOT NULL DEFAULT ''
);

-- Insert default settings
INSERT INTO app_settings (key, value) VALUES ('emi_rate', '12')
ON CONFLICT (key) DO NOTHING;

-- 7. PASSWORD RESETS
CREATE TABLE IF NOT EXISTS password_resets (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       VARCHAR NOT NULL UNIQUE,
    expires_at  DOUBLE PRECISION NOT NULL,
    used        INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pw_resets_token ON password_resets (token);
CREATE INDEX IF NOT EXISTS idx_pw_resets_user ON password_resets (user_id);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
-- By default Supabase enables RLS on new tables. Since this app
-- uses the service_role key server-side, RLS is bypassed.
-- If you later switch to the anon key, add appropriate policies.
--
-- To disable RLS for server-side admin access:
ALTER TABLE users            ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_logs       ENABLE ROW LEVEL SECURITY;
ALTER TABLE bookings         ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages         ENABLE ROW LEVEL SECURITY;
ALTER TABLE app_settings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_resets  ENABLE ROW LEVEL SECURITY;

-- Allow service_role full access (these policies apply to
-- authenticated requests when using anon key):
CREATE POLICY "Service role full access" ON users
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON password_history
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON login_logs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON bookings
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON messages
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON app_settings
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON password_resets
    FOR ALL USING (true) WITH CHECK (true);
