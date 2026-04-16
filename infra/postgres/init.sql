-- StreamRec PostgreSQL schema
-- Maps to: Amazon RDS (PostgreSQL) or Aurora in production
-- DynamoDB alternative noted per table where applicable

-- -------------------------------------------------------------------------
-- Item catalog
-- DynamoDB alternative: single-table design with PK=item_id
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS items (
    item_id         VARCHAR(64)     PRIMARY KEY,
    title           TEXT            NOT NULL,
    category        VARCHAR(128)    NOT NULL,
    subcategory     VARCHAR(128),
    price           NUMERIC(10, 2)  NOT NULL,
    avg_rating      NUMERIC(3, 2),
    review_count    INTEGER         DEFAULT 0,
    tags            TEXT[],
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);

-- -------------------------------------------------------------------------
-- User profiles
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id         VARCHAR(64)     PRIMARY KEY,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    metadata        JSONB           DEFAULT '{}'
);

-- -------------------------------------------------------------------------
-- Raw event log (append-only, partitionable by month in production)
-- DynamoDB alternative: TTL-enabled table, GSI on user_id + timestamp
-- S3 alternative: Parquet files partitioned by date for batch training
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    event_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(64)     NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_type      VARCHAR(32)     NOT NULL,
    item_id         VARCHAR(64)     REFERENCES items(item_id) ON DELETE SET NULL,
    session_id      VARCHAR(128),
    query           TEXT,
    rating          NUMERIC(3, 2),
    metadata        JSONB           DEFAULT '{}',
    timestamp       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    ingested_at     TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_user_id   ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_item_id   ON events(item_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_type      ON events(event_type);
-- Composite: user's recent events by type
CREATE INDEX IF NOT EXISTS idx_events_user_type ON events(user_id, event_type, timestamp DESC);

-- -------------------------------------------------------------------------
-- User-item interaction matrix (denormalized, updated by batch pipeline)
-- Used for collaborative filtering training
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_item_interactions (
    user_id         VARCHAR(64)     NOT NULL,
    item_id         VARCHAR(64)     NOT NULL,
    interaction_score NUMERIC(6, 3) NOT NULL DEFAULT 0,  -- weighted sum of EVENT_WEIGHTS
    view_count      INTEGER         DEFAULT 0,
    cart_count      INTEGER         DEFAULT 0,
    purchase_count  INTEGER         DEFAULT 0,
    last_interacted TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (user_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_uii_user ON user_item_interactions(user_id);
CREATE INDEX IF NOT EXISTS idx_uii_item ON user_item_interactions(item_id);
CREATE INDEX IF NOT EXISTS idx_uii_score ON user_item_interactions(interaction_score DESC);

-- -------------------------------------------------------------------------
-- Model registry — tracks trained model versions
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS model_registry (
    model_id        SERIAL          PRIMARY KEY,
    model_name      VARCHAR(64)     NOT NULL,
    version         VARCHAR(32)     NOT NULL,
    artifact_path   TEXT            NOT NULL,  -- local path or s3:// URI
    metrics         JSONB           DEFAULT '{}',
    trained_at      TIMESTAMPTZ     DEFAULT NOW(),
    is_active       BOOLEAN         DEFAULT FALSE,
    UNIQUE (model_name, version)
);

-- -------------------------------------------------------------------------
-- Helper functions
-- -------------------------------------------------------------------------

-- Upsert interaction score (called from stream processor)
CREATE OR REPLACE FUNCTION upsert_interaction(
    p_user_id VARCHAR,
    p_item_id VARCHAR,
    p_score_delta NUMERIC,
    p_event_type VARCHAR
) RETURNS VOID AS $$
BEGIN
    INSERT INTO user_item_interactions
        (user_id, item_id, interaction_score, view_count, cart_count, purchase_count, last_interacted)
    VALUES (
        p_user_id,
        p_item_id,
        p_score_delta,
        CASE WHEN p_event_type = 'product_view' THEN 1 ELSE 0 END,
        CASE WHEN p_event_type = 'add_to_cart'  THEN 1 ELSE 0 END,
        CASE WHEN p_event_type = 'purchase'      THEN 1 ELSE 0 END,
        NOW()
    )
    ON CONFLICT (user_id, item_id) DO UPDATE SET
        interaction_score = user_item_interactions.interaction_score + p_score_delta,
        view_count    = user_item_interactions.view_count    + CASE WHEN p_event_type = 'product_view' THEN 1 ELSE 0 END,
        cart_count    = user_item_interactions.cart_count    + CASE WHEN p_event_type = 'add_to_cart'  THEN 1 ELSE 0 END,
        purchase_count = user_item_interactions.purchase_count + CASE WHEN p_event_type = 'purchase'   THEN 1 ELSE 0 END,
        last_interacted = NOW();
END;
$$ LANGUAGE plpgsql;
