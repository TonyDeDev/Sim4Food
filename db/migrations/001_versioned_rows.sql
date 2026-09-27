-- Ingredients and recipes keep their own history.
--
-- When a versioned value changes, the old values stay in the table as a row
-- with valid_to set and the new values become the current row. A row was in
-- force for valid_from <= t < valid_to. The first version of a row has
-- valid_from = 1900-01-01 so it covers all earlier history.
--
-- ingredients: the current row keeps its id (purchases, counts and recipes
--   reference it). History rows point at it through current_id and are never
--   referenced by anything else. current_id IS NULL means "the current row".
-- recipes: a changed line ends the current row (valid_to) and adds a new one.
--
-- Additive and idempotent. Existing rows become the first (current) version.

-- Earlier draft of this feature used separate log tables; drop them if present.
DROP TABLE IF EXISTS ingredient_changes;
DROP TABLE IF EXISTS recipe_changes;

ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE menu_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT '1900-01-01';
ALTER TABLE ingredients ALTER COLUMN valid_from SET DEFAULT now();
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;
ALTER TABLE ingredients ADD COLUMN IF NOT EXISTS current_id UUID REFERENCES ingredients(id) ON DELETE CASCADE;

ALTER TABLE ingredients DROP CONSTRAINT IF EXISTS ingredients_history_check;
ALTER TABLE ingredients ADD CONSTRAINT ingredients_history_check
    CHECK ((current_id IS NULL) = (valid_to IS NULL) AND (valid_to IS NULL OR valid_to >= valid_from));
CREATE UNIQUE INDEX IF NOT EXISTS ingredients_current_key ON ingredients (restaurant_id, external_id) WHERE current_id IS NULL;
ALTER TABLE ingredients DROP CONSTRAINT IF EXISTS ingredients_restaurant_id_external_id_key;
CREATE INDEX IF NOT EXISTS idx_ingredients_current_id ON ingredients (current_id) WHERE current_id IS NOT NULL;

ALTER TABLE recipes ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ NOT NULL DEFAULT '1900-01-01';
ALTER TABLE recipes ALTER COLUMN valid_from SET DEFAULT now();
ALTER TABLE recipes ADD COLUMN IF NOT EXISTS valid_to TIMESTAMPTZ;

ALTER TABLE recipes DROP CONSTRAINT IF EXISTS recipes_history_check;
ALTER TABLE recipes ADD CONSTRAINT recipes_history_check CHECK (valid_to IS NULL OR valid_to >= valid_from);
CREATE UNIQUE INDEX IF NOT EXISTS recipes_current_key ON recipes (menu_item_id, ingredient_id) WHERE valid_to IS NULL;
ALTER TABLE recipes DROP CONSTRAINT IF EXISTS recipes_menu_item_id_ingredient_id_key;
