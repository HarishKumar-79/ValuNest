-- ============================================================
-- Migration 001: Add roles and coordinates
-- ============================================================
-- Safe to run multiple times. Uses IF NOT EXISTS / exception handling.
-- Run in Supabase SQL Editor (Dashboard → SQL Editor).
-- ============================================================

-- 1. Add 'role' column to users table
DO $$
BEGIN
    ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'user';
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- 2. Add coordinate columns to bookings table
DO $$
BEGIN
    ALTER TABLE bookings ADD COLUMN latitude DOUBLE PRECISION DEFAULT NULL;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE bookings ADD COLUMN longitude DOUBLE PRECISION DEFAULT NULL;
EXCEPTION
    WHEN duplicate_column THEN NULL;
END $$;

-- 3. Add RLS policy for new columns (same pattern as existing)
-- No new tables, so no new policies needed.

-- ============================================================
-- Verification: Run this to confirm columns exist
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'users' AND column_name = 'role';
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'bookings' AND column_name IN ('latitude', 'longitude');
-- ============================================================
