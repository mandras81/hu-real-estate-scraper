-- 002_consolidation_layer.sql
-- Consolidation / Entity Resolution layer
-- Implements PLAN.md 4-Stage Resolution Cascade:
--   1. Blocking filter (city + property_type + rooms)
--   2. Deterministic matching (area +/-15% + rooms match)
--   3. Probabilistic text matching (pg_trgm on description)
--   4. Visual validation (image pHash -- future placeholder)

-- ============================================================
-- TABLE: properties -- Golden Record for a unique physical property
-- ============================================================
CREATE TABLE IF NOT EXISTS properties (
    id              SERIAL PRIMARY KEY,
    property_type   TEXT,
    city            TEXT,
    district        TEXT,
    postal_code     TEXT,
    area_sqm        NUMERIC,
    rooms           TEXT,
    floor           INTEGER,
    total_floors    INTEGER,
    lat             NUMERIC,
    lng             NUMERIC,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'removed')),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    match_checksum  TEXT
);

CREATE INDEX IF NOT EXISTS idx_properties_city_type
    ON properties (city, property_type);
CREATE INDEX IF NOT EXISTS idx_properties_status
    ON properties (status);
CREATE INDEX IF NOT EXISTS idx_properties_match_checksum
    ON properties (match_checksum);

-- ============================================================
-- TABLE: property_sources -- Links properties <-> listings
-- ============================================================
CREATE TABLE IF NOT EXISTS property_sources (
    id              SERIAL PRIMARY KEY,
    property_id     INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    listing_id      INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    confidence      NUMERIC(4,3) NOT NULL DEFAULT 1.0,
    match_method    TEXT NOT NULL DEFAULT 'direct'
                    CHECK (match_method IN ('direct', 'deterministic', 'text', 'image', 'manual')),
    matched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (listing_id),
    UNIQUE (property_id, source, source_url)
);

CREATE INDEX IF NOT EXISTS idx_property_sources_property
    ON property_sources (property_id);
CREATE INDEX IF NOT EXISTS idx_property_sources_listing
    ON property_sources (listing_id);
CREATE INDEX IF NOT EXISTS idx_property_sources_confidence
    ON property_sources (confidence DESC);

-- ============================================================
-- TABLE: price_history -- Delta-only price changes
-- ============================================================
CREATE TABLE IF NOT EXISTS price_history (
    id              SERIAL PRIMARY KEY,
    property_id     INTEGER NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    listing_id      INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    source          TEXT NOT NULL,
    price           INTEGER,
    price_per_sqm   INTEGER,
    currency        TEXT DEFAULT 'HUF',
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_history_property
    ON price_history (property_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_price_history_recorded
    ON price_history (recorded_at);

-- ============================================================
-- TABLE: property_matches -- Staging for cross-source candidates
-- ============================================================
CREATE TABLE IF NOT EXISTS property_matches (
    id                  SERIAL PRIMARY KEY,
    listing_id_a        INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    listing_id_b        INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
    blocking_key        TEXT,
    deterministic_score NUMERIC(5,4),
    text_similarity     NUMERIC(5,4),
    image_similarity    NUMERIC(5,4),
    combined_score      NUMERIC(5,4),
    match_status        TEXT NOT NULL DEFAULT 'pending'
                        CHECK (match_status IN ('pending', 'confirmed', 'rejected')),
    reviewed_at         TIMESTAMPTZ,

    UNIQUE (listing_id_a, listing_id_b)
);

CREATE INDEX IF NOT EXISTS idx_property_matches_status
    ON property_matches (match_status, combined_score DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_property_matches_blocking
    ON property_matches (blocking_key);

-- ============================================================
-- FUNCTION: generate_match_checksum()
-- ============================================================
CREATE OR REPLACE FUNCTION generate_match_checksum(
    p_city TEXT,
    p_property_type TEXT,
    p_area_sqm NUMERIC,
    p_rooms TEXT
) RETURNS TEXT AS $FUNC$
BEGIN
    RETURN ENCODE(
        HMAC(
            COALESCE(p_city, '') || '|' ||
            COALESCE(p_property_type, '') || '|' ||
            COALESCE(ROUND(p_area_sqm::NUMERIC, 0)::TEXT, '') || '|' ||
            COALESCE(p_rooms, ''),
            'realestate::match',
            'sha256'
        ),
        'hex'
    );
END;
$FUNC$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================
-- FUNCTION: find_property_matches() -- Stage 1-2-3 matching
-- ============================================================
CREATE OR REPLACE FUNCTION find_property_matches()
RETURNS INTEGER AS $FUNC$
DECLARE
    match_count INTEGER := 0;
BEGIN
    DELETE FROM property_matches WHERE match_status = 'pending';

    INSERT INTO property_matches (
        listing_id_a, listing_id_b, blocking_key,
        deterministic_score, text_similarity, combined_score, match_status
    )
    SELECT
        l1.id, l2.id,
        COALESCE(l1.city, '') || '|' || COALESCE(l1.property_type, '') || '|' || COALESCE(l1.rooms, ''),
        CASE
            WHEN (l1.area_sqm IS NOT NULL AND l2.area_sqm IS NOT NULL
                  AND l1.area_sqm BETWEEN l2.area_sqm * 0.85 AND l2.area_sqm * 1.15
                  AND l1.rooms = l2.rooms)
            THEN 0.9::NUMERIC(5,4)
            ELSE 0.0::NUMERIC(5,4)
        END,
        CASE
            WHEN l1.description IS NOT NULL AND l2.description IS NOT NULL
                 AND length(l1.description) > 20 AND length(l2.description) > 20
            THEN SIMILARITY(l1.description, l2.description)::NUMERIC(5,4)
            ELSE 0.0::NUMERIC(5,4)
        END,
        0.0::NUMERIC(5,4),
        'pending'
    FROM listings l1
    JOIN listings l2
        ON l1.id < l2.id
        AND l1.source != l2.source
        AND l1.city = l2.city
        AND l1.property_type = l2.property_type
        AND l1.rooms IS NOT NULL AND l2.rooms IS NOT NULL
        AND l1.rooms = l2.rooms
        AND l1.area_sqm IS NOT NULL AND l2.area_sqm IS NOT NULL
        AND l1.area_sqm BETWEEN l2.area_sqm * 0.7 AND l2.area_sqm * 1.3
    WHERE l1.is_active = TRUE AND l2.is_active = TRUE
    ON CONFLICT (listing_id_a, listing_id_b)
    DO UPDATE SET
        deterministic_score = EXCLUDED.deterministic_score,
        text_similarity = EXCLUDED.text_similarity,
        blocking_key = EXCLUDED.blocking_key;

    GET DIAGNOSTICS match_count = ROW_COUNT;

    UPDATE property_matches
    SET combined_score = ROUND(
        (COALESCE(deterministic_score, 0) * 0.7 +
         COALESCE(text_similarity, 0) * 0.3)::NUMERIC, 4
    )
    WHERE match_status = 'pending';

    RETURN match_count;
END;
$FUNC$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: auto_confirm_matches() -- High-confidence -> confirmed
-- ============================================================
CREATE OR REPLACE FUNCTION auto_confirm_matches()
RETURNS INTEGER AS $FUNC$
DECLARE
    confirmed_count INTEGER := 0;
BEGIN
    UPDATE property_matches
    SET match_status = 'confirmed', reviewed_at = NOW()
    WHERE match_status = 'pending'
      AND deterministic_score >= 0.9
      AND text_similarity >= 0.3;

    GET DIAGNOSTICS confirmed_count = ROW_COUNT;
    RETURN confirmed_count;
END;
$FUNC$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: build_or_update_properties() -- Merge matches into golden records
-- ============================================================
CREATE OR REPLACE FUNCTION build_or_update_properties()
RETURNS INTEGER AS $FUNC$
DECLARE
    prop_count INTEGER := 0;
    r RECORD;
    pid INTEGER;
BEGIN
    -- Part A: Unlinked listings -> new standalone properties
    FOR r IN
        SELECT l.* FROM listings l
        WHERE l.is_active = TRUE
          AND NOT EXISTS (SELECT 1 FROM property_sources ps WHERE ps.listing_id = l.id)
    LOOP
        INSERT INTO properties (
            property_type, city, district, area_sqm, rooms,
            floor, total_floors, lat, lng,
            status, first_seen_at, last_seen_at, is_active,
            match_checksum
        ) VALUES (
            r.property_type, r.city, r.district, r.area_sqm, r.rooms,
            r.floor, r.total_floors, r.lat, r.lng,
            'active', COALESCE(r.scraped_at, NOW()), NOW(), TRUE,
            generate_match_checksum(r.city, r.property_type, r.area_sqm, r.rooms)
        )
        RETURNING id INTO pid;

        INSERT INTO property_sources (property_id, listing_id, source, source_url, match_method, is_primary)
        VALUES (pid, r.id, r.source, r.source_url, 'direct', TRUE);

        INSERT INTO price_history (property_id, listing_id, source, price, price_per_sqm, currency)
        VALUES (pid, r.id, r.source, r.price, r.price_per_sqm, r.currency);

        prop_count := prop_count + 1;
    END LOOP;

    -- Part B: Confirmed cross-source matches -> merge into shared property
    FOR r IN
        SELECT pm.id AS match_id,
               l1.id AS listing_id_1, l1.source AS source_1, l1.source_url AS url_1,
               l2.id AS listing_id_2, l2.source AS source_2, l2.source_url AS url_2,
               COALESCE(l1.property_type, l2.property_type) AS prop_type,
               COALESCE(l1.city, l2.city) AS city_v,
               COALESCE(l1.area_sqm, l2.area_sqm) AS area_v,
               COALESCE(l1.rooms, l2.rooms) AS rooms_v
        FROM property_matches pm
        JOIN listings l1 ON l1.id = pm.listing_id_a
        JOIN listings l2 ON l2.id = pm.listing_id_b
        WHERE pm.match_status = 'confirmed'
    LOOP
        -- Neither assigned: create new shared golden record
        IF NOT EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_1)
           AND NOT EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_2)
        THEN
            INSERT INTO properties (
                property_type, city, area_sqm, rooms,
                status, first_seen_at, last_seen_at, is_active,
                match_checksum
            ) VALUES (
                r.prop_type, r.city_v, r.area_v, r.rooms_v,
                'active', NOW(), NOW(), TRUE,
                generate_match_checksum(r.city_v, r.prop_type, r.area_v, r.rooms_v)
            )
            RETURNING id INTO pid;

            INSERT INTO property_sources (property_id, listing_id, source, source_url, match_method, confidence, is_primary)
            VALUES (pid, r.listing_id_1, r.source_1, r.url_1, 'deterministic', 0.9, TRUE);
            INSERT INTO price_history (property_id, listing_id, source, price, price_per_sqm, currency)
            SELECT pid, id, source, price, price_per_sqm, currency FROM listings WHERE id = r.listing_id_1;

            INSERT INTO property_sources (property_id, listing_id, source, source_url, match_method, confidence, is_primary)
            VALUES (pid, r.listing_id_2, r.source_2, r.url_2, 'deterministic', 0.85, FALSE);
            INSERT INTO price_history (property_id, listing_id, source, price, price_per_sqm, currency)
            SELECT pid, id, source, price, price_per_sqm, currency FROM listings WHERE id = r.listing_id_2;

            prop_count := prop_count + 1;

        -- Listing 1 already has a property: add listing 2
        ELSIF EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_1)
          AND NOT EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_2)
        THEN
            SELECT property_id INTO pid FROM property_sources WHERE listing_id = r.listing_id_1;
            INSERT INTO property_sources (property_id, listing_id, source, source_url, match_method, confidence, is_primary)
            VALUES (pid, r.listing_id_2, r.source_2, r.url_2, 'deterministic', 0.85, FALSE)
            ON CONFLICT (listing_id) DO NOTHING;
            INSERT INTO price_history (property_id, listing_id, source, price, price_per_sqm, currency)
            SELECT pid, id, source, price, price_per_sqm, currency FROM listings WHERE id = r.listing_id_2;
            UPDATE properties SET last_seen_at = NOW() WHERE id = pid;
            prop_count := prop_count + 1;

        -- Listing 2 already has a property: add listing 1
        ELSIF NOT EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_1)
          AND EXISTS (SELECT 1 FROM property_sources WHERE listing_id = r.listing_id_2)
        THEN
            SELECT property_id INTO pid FROM property_sources WHERE listing_id = r.listing_id_2;
            INSERT INTO property_sources (property_id, listing_id, source, source_url, match_method, confidence, is_primary)
            VALUES (pid, r.listing_id_1, r.source_1, r.url_1, 'deterministic', 0.85, FALSE)
            ON CONFLICT (listing_id) DO NOTHING;
            INSERT INTO price_history (property_id, listing_id, source, price, price_per_sqm, currency)
            SELECT pid, id, source, price, price_per_sqm, currency FROM listings WHERE id = r.listing_id_1;
            UPDATE properties SET last_seen_at = NOW() WHERE id = pid;
            prop_count := prop_count + 1;
        END IF;
    END LOOP;

    RETURN prop_count;
END;
$FUNC$ LANGUAGE plpgsql;

-- ============================================================
-- FUNCTION: refresh_consolidation() -- One-shot full run
-- ============================================================
CREATE OR REPLACE FUNCTION refresh_consolidation()
RETURNS TEXT AS $FUNC$
DECLARE
    matches_found INTEGER;
    confirmed INTEGER;
    properties_built INTEGER;
BEGIN
    SELECT find_property_matches() INTO matches_found;
    SELECT auto_confirm_matches() INTO confirmed;
    SELECT build_or_update_properties() INTO properties_built;
    RETURN format('matches: %s, auto-confirmed: %s, properties built/updated: %s',
                  matches_found, confirmed, properties_built);
END;
$FUNC$ LANGUAGE plpgsql;

-- ============================================================
-- VIEW: v_properties_enriched -- The canonical query target
-- ============================================================
CREATE OR REPLACE VIEW v_properties_enriched AS
SELECT
    p.id AS property_id,
    p.property_type,
    p.city,
    p.district,
    p.area_sqm,
    p.rooms,
    p.floor,
    p.total_floors,
    p.lat,
    p.lng,
    p.status,
    p.first_seen_at,
    p.last_seen_at,
    p.is_active,
    COUNT(ps.id)::INT AS source_count,
    ARRAY_AGG(DISTINCT ps.source ORDER BY ps.source) AS sources,
    (SELECT ph.price FROM price_history ph
     WHERE ph.property_id = p.id
     ORDER BY ph.recorded_at DESC LIMIT 1) AS current_price,
    (SELECT ph.price FROM price_history ph
     WHERE ph.property_id = p.id
     ORDER BY ph.recorded_at ASC LIMIT 1) AS first_seen_price
FROM properties p
LEFT JOIN property_sources ps ON ps.property_id = p.id
GROUP BY p.id
ORDER BY p.last_seen_at DESC;

-- =========================================================
