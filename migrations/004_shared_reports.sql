-- SmartCSV: shared reports migration
-- Run this in your Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS shared_reports (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    share_token     TEXT NOT NULL UNIQUE,
    processed_key   TEXT NOT NULL,
    title           TEXT,
    expires_at      TIMESTAMPTZ,
    view_count      INTEGER NOT NULL DEFAULT 0,
    is_public       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_shared_reports_token ON shared_reports (share_token);

-- RLS
ALTER TABLE shared_reports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own reports"
    ON shared_reports FOR ALL
    USING (auth.uid() = user_id);

-- Public access for viewing shared reports (via share_token)
CREATE POLICY "Anyone can view public reports"
    ON shared_reports FOR SELECT
    USING (is_public = true);
