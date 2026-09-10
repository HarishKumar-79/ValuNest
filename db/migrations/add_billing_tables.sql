-- ============================================================
-- Migration: Add Billing & EMI Payments tables
-- ============================================================
-- Run this in Supabase SQL Editor (Dashboard → SQL Editor)
-- Safe to run on existing databases — won't affect other tables.
-- ============================================================

-- 1. BILLING (Invoice records)
CREATE TABLE IF NOT EXISTS billing (
    id              BIGSERIAL PRIMARY KEY,
    booking_id      BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invoice_number  VARCHAR NOT NULL UNIQUE,
    billing_name    VARCHAR NOT NULL DEFAULT '',
    billing_email   VARCHAR NOT NULL DEFAULT '',
    billing_phone   VARCHAR DEFAULT '',
    billing_address TEXT DEFAULT '',
    subtotal        DOUBLE PRECISION NOT NULL DEFAULT 0,
    tax_rate        DOUBLE PRECISION NOT NULL DEFAULT 0,
    tax_amount      DOUBLE PRECISION NOT NULL DEFAULT 0,
    discount        DOUBLE PRECISION NOT NULL DEFAULT 0,
    total           DOUBLE PRECISION NOT NULL DEFAULT 0,
    payment_method  VARCHAR DEFAULT '',
    payment_status  VARCHAR DEFAULT 'paid',
    notes           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_billing_booking ON billing (booking_id);
CREATE INDEX IF NOT EXISTS idx_billing_user ON billing (user_id);
CREATE INDEX IF NOT EXISTS idx_billing_invoice ON billing (invoice_number);
CREATE INDEX IF NOT EXISTS idx_billing_status ON billing (payment_status);

-- 2. EMI PAYMENTS (Installment tracking)
CREATE TABLE IF NOT EXISTS emi_payments (
    id              BIGSERIAL PRIMARY KEY,
    billing_id      BIGINT NOT NULL REFERENCES billing(id) ON DELETE CASCADE,
    booking_id      BIGINT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    installment_no  INTEGER NOT NULL,
    due_date        DATE NOT NULL,
    amount_due      DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount_paid     DOUBLE PRECISION NOT NULL DEFAULT 0,
    penalty         DOUBLE PRECISION NOT NULL DEFAULT 0,
    status          VARCHAR DEFAULT 'pending',
    paid_at         TIMESTAMPTZ,
    txn_id          VARCHAR DEFAULT '',
    payment_method  VARCHAR DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_emi_billing ON emi_payments (billing_id);
CREATE INDEX IF NOT EXISTS idx_emi_booking ON emi_payments (booking_id);
CREATE INDEX IF NOT EXISTS idx_emi_user ON emi_payments (user_id);
CREATE INDEX IF NOT EXISTS idx_emi_status ON emi_payments (status);
CREATE INDEX IF NOT EXISTS idx_emi_due_date ON emi_payments (due_date);

-- 3. Enable RLS
ALTER TABLE billing      ENABLE ROW LEVEL SECURITY;
ALTER TABLE emi_payments ENABLE ROW LEVEL SECURITY;

-- 4. Allow service_role full access
CREATE POLICY "Service role full access" ON billing
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access" ON emi_payments
    FOR ALL USING (true) WITH CHECK (true);
