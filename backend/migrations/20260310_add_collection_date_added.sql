ALTER TABLE collections
ADD COLUMN IF NOT EXISTS date_added TIMESTAMPTZ DEFAULT NOW();

-- Seed existing rows with random dates between now and ~180 days ago.
UPDATE collections
SET date_added = NOW()
  - ((random() * 180)::int || ' days')::interval
  - ((random() * 23)::int || ' hours')::interval
WHERE date_added IS NULL;

ALTER TABLE collections
ALTER COLUMN date_added SET NOT NULL;
