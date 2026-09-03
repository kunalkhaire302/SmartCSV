-- Migration: 006_improvements.sql
-- SmartCSV Database Improvements
-- Adds atomic RPCs, indexes for performance, and quota counting optimization.

-- 1. Atomic view increment for shared reports
CREATE OR REPLACE FUNCTION increment_share_views(p_share_token UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE shared_reports
    SET view_count = COALESCE(view_count, 0) + 1
    WHERE share_token = p_share_token;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2. Performance indexes for frequent queries
-- Used by count_user_uploads_this_month
CREATE INDEX IF NOT EXISTS idx_uploads_user_created_at ON uploads(user_id, created_at);

-- Used by count_user_ai_requests_this_month
CREATE INDEX IF NOT EXISTS idx_llm_usage_user_created_at ON llm_usage(user_id, created_at);

-- Used for fast lookups by storage keys
CREATE INDEX IF NOT EXISTS idx_uploads_storage_key ON uploads(storage_key);
CREATE INDEX IF NOT EXISTS idx_uploads_processed_key ON uploads(processed_key);

-- 3. Cleanup unused column in users
-- We no longer use uploads_this_month for quota counting, it's calculated dynamically.
-- But to preserve backwards compatibility, we won't drop it yet.
-- ALTER TABLE users DROP COLUMN IF EXISTS uploads_this_month;
