CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE upload_file_type AS ENUM ('sales', 'purchases', 'inventory_counts', 'ingredients', 'menu', 'recipes', 'events', 'customer_profile');
CREATE TYPE upload_status AS ENUM ('pending', 'processed', 'failed');
CREATE TYPE count_source AS ENUM ('manual', 'computed');
CREATE TYPE event_type AS ENUM ('holiday', 'deal');

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_sessions_user ON sessions (user_id);

-- One user can own several restaurants (the dashboard supports multiple
-- businesses), so name is unique per owner rather than globally.
CREATE TABLE restaurants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    business_type TEXT,
    location TEXT,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (owner_user_id, name)
);

CREATE TABLE ingredients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_cost NUMERIC(10, 2) NOT NULL,
    pack_size NUMERIC(10, 3) NOT NULL,
    shelf_life_days INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- History lives in this table: a changed unit / unit_cost / pack_size /
    -- shelf_life_days leaves the old values behind as a row with valid_to set
    -- and current_id pointing at the current row. The first version starts at
    -- 1900-01-01. Everything else references the current row's id.
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    current_id UUID REFERENCES ingredients(id) ON DELETE CASCADE,
    CONSTRAINT ingredients_history_check
        CHECK ((current_id IS NULL) = (valid_to IS NULL) AND (valid_to IS NULL OR valid_to >= valid_from))
);
CREATE UNIQUE INDEX ingredients_current_key ON ingredients (restaurant_id, external_id) WHERE current_id IS NULL;
CREATE INDEX idx_ingredients_current_id ON ingredients (current_id) WHERE current_id IS NOT NULL;

CREATE TABLE menu_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    external_id TEXT NOT NULL,
    name TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    category TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (restaurant_id, external_id)
);

CREATE TABLE recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    menu_item_id UUID NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    ingredient_id UUID NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    qty_per_serving NUMERIC(10, 4) NOT NULL,
    -- A changed quantity ends this row (valid_to) and adds a new one. valid_to
    -- NULL is the current line. The first version starts at 1900-01-01.
    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to TIMESTAMPTZ,
    CONSTRAINT recipes_history_check CHECK (valid_to IS NULL OR valid_to >= valid_from)
);
CREATE UNIQUE INDEX recipes_current_key ON recipes (menu_item_id, ingredient_id) WHERE valid_to IS NULL;

CREATE TABLE upload_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    file_type upload_file_type NOT NULL,
    file_name TEXT,
    row_count INT,
    status upload_status NOT NULL DEFAULT 'pending',
    error_message TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sales (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    menu_item_id UUID NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    qty_sold NUMERIC(10, 2) NOT NULL,
    avg_price NUMERIC(10, 2) NOT NULL,
    upload_batch_id UUID REFERENCES upload_batches(id) ON DELETE SET NULL
);
CREATE INDEX idx_sales_restaurant_date ON sales (restaurant_id, date);

CREATE TABLE purchases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    ingredient_id UUID NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    qty NUMERIC(10, 3) NOT NULL,
    unit_cost NUMERIC(10, 2) NOT NULL,
    total NUMERIC(10, 2) NOT NULL,
    upload_batch_id UUID REFERENCES upload_batches(id) ON DELETE SET NULL
);
CREATE INDEX idx_purchases_restaurant_date ON purchases (restaurant_id, date);

CREATE TABLE inventory_counts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    ingredient_id UUID NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    qty_on_hand NUMERIC(10, 3) NOT NULL,
    source count_source NOT NULL DEFAULT 'manual',
    upload_batch_id UUID REFERENCES upload_batches(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inventory_counts_restaurant_ingredient_date ON inventory_counts (restaurant_id, ingredient_id, date);

CREATE TABLE inventory_current (
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    ingredient_id UUID NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    qty_on_hand NUMERIC(10, 3) NOT NULL,
    last_reconciled_count_id UUID REFERENCES inventory_counts(id),
    last_updated TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (restaurant_id, ingredient_id)
);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    type event_type NOT NULL,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    items UUID[] DEFAULT '{}',
    discount_pct NUMERIC(5, 2),
    expected_lift NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_events_restaurant_dates ON events (restaurant_id, start_date, end_date);

CREATE TABLE customer_profiles (
    restaurant_id UUID PRIMARY KEY REFERENCES restaurants(id) ON DELETE CASCADE,
    daily_customers_estimate NUMERIC(10, 2),
    busy_days TEXT[],
    segments JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE calibration_params (
    restaurant_id UUID PRIMARY KEY REFERENCES restaurants(id) ON DELETE CASCADE,
    params JSONB NOT NULL,
    calibrated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE simulation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    scenario_params JSONB NOT NULL,
    results JSONB NOT NULL,
    replay_log JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_simulation_runs_restaurant_created ON simulation_runs (restaurant_id, created_at DESC);

CREATE TABLE backtest_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    restaurant_id UUID NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
    results JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
