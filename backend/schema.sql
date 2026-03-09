-- Supabase Postgres schema for Pokemon card app
-- Requires pgcrypto for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE sets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    release_date DATE
);

CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    set_id TEXT NOT NULL REFERENCES sets(id) ON DELETE CASCADE,
    card_number TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (set_id, card_number)
);

CREATE TABLE card_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    storage_bucket TEXT NOT NULL DEFAULT 'pokemon-images',
    storage_path TEXT NOT NULL UNIQUE
);

CREATE TABLE collections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    card_id TEXT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 1
);

-- Example inserts
INSERT INTO sets (id, name, release_date)
VALUES ('sv1', 'Scarlet & Violet', '2023-03-31');

INSERT INTO cards (id, set_id, card_number, name)
VALUES ('sv1-43', 'sv1', '43', 'Gardevoir ex');

INSERT INTO card_images (card_id, storage_path)
VALUES ('sv1-43', 'sv1/gardevoir-ex-43.webp');

INSERT INTO collections (user_id, card_id, quantity)
VALUES ('11111111-1111-1111-1111-111111111111', 'sv1-43', 2);

-- Example verification queries
SELECT * FROM sets;
SELECT * FROM cards;
SELECT * FROM card_images;
SELECT * FROM collections;

SELECT
    c.id AS card_id,
    c.name AS card_name,
    s.name AS set_name,
    ci.storage_bucket,
    ci.storage_path
FROM cards c
JOIN sets s ON s.id = c.set_id
LEFT JOIN card_images ci ON ci.card_id = c.id;
