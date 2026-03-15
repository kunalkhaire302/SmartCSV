-- SmartCSV: users table migration
-- Run this in your Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY REFERENCES auth.users(id),
    email               TEXT,
    plan                TEXT NOT NULL DEFAULT 'free'
                        CHECK (plan IN ('free', 'pro', 'team')),
    stripe_customer_id  TEXT,
    uploads_this_month  INTEGER NOT NULL DEFAULT 0,
    month_reset_at      TIMESTAMPTZ DEFAULT date_trunc('month', now()) + INTERVAL '1 month',
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- RLS: users can read their own record
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own profile"
    ON users FOR SELECT
    USING (auth.uid() = id);

-- Auto-create a user row on first sign-up via trigger
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email)
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Attach trigger to auth.users
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
