-- SmartCSV: LLM usage tracking migration
-- Run this in your Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS llm_usage (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES auth.users(id),
    model           TEXT NOT NULL DEFAULT 'claude-sonnet-4-5',
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    purpose         TEXT NOT NULL DEFAULT 'summary',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_user_id ON llm_usage (user_id);

-- View for monthly summary counts per user
CREATE OR REPLACE VIEW monthly_ai_usage AS
SELECT
    user_id,
    COUNT(*) AS summaries_this_month,
    SUM(tokens_used) AS tokens_this_month
FROM llm_usage
WHERE created_at >= date_trunc('month', now())
GROUP BY user_id;

-- RLS
ALTER TABLE llm_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own usage"
    ON llm_usage FOR SELECT
    USING (auth.uid() = user_id);
