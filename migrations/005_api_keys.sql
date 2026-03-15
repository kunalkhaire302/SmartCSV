-- SmartCSV: API keys table migration
-- Run this in your Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS api_keys (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    key_hash        TEXT NOT NULL UNIQUE,      -- SHA-256 hash of the key
    key_prefix      TEXT NOT NULL,              -- First 8 chars for display (e.g. "sk_live_Ab12...")
    name            TEXT DEFAULT 'Default',
    last_used_at    TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys (user_id);

-- RLS
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own keys"
    ON api_keys FOR ALL
    USING (auth.uid() = user_id);
