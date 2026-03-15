-- SmartCSV: uploads table migration
-- Run this in your Supabase SQL Editor (or any Postgres client).

CREATE TABLE IF NOT EXISTS uploads (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL,
    original_name   TEXT NOT NULL,
    storage_key     TEXT NOT NULL,
    processed_key   TEXT,
    row_count       INTEGER,
    column_count    INTEGER,
    size_bytes      BIGINT,
    status          TEXT NOT NULL DEFAULT 'uploaded'
                    CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Index for fast user-scoped queries
CREATE INDEX IF NOT EXISTS idx_uploads_user_id ON uploads (user_id);

-- Row-Level Security: users can only see their own uploads
ALTER TABLE uploads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own uploads"
    ON uploads FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own uploads"
    ON uploads FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own uploads"
    ON uploads FOR UPDATE
    USING (auth.uid() = user_id);
