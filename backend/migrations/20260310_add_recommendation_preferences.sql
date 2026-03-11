CREATE TABLE IF NOT EXISTS recommendation_preferences (
  user_id UUID PRIMARY KEY,
  budget_policy TEXT NOT NULL DEFAULT 'soft_cap',
  budget_usd NUMERIC NOT NULL DEFAULT 1000,
  num INTEGER NOT NULL DEFAULT 10,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE recommendation_preferences
DROP CONSTRAINT IF EXISTS recommendation_preferences_budget_policy_check;

ALTER TABLE recommendation_preferences
ADD CONSTRAINT recommendation_preferences_budget_policy_check
CHECK (budget_policy IN ('soft_cap', 'strict_cap', 'market_flex'));

ALTER TABLE recommendation_preferences
DROP CONSTRAINT IF EXISTS recommendation_preferences_num_check;

ALTER TABLE recommendation_preferences
ADD CONSTRAINT recommendation_preferences_num_check
CHECK (num >= 1 AND num <= 15);
