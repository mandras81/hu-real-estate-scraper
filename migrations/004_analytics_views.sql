-- ============================================================================
-- Migration 004: Analytics Views + District parsing for Grafana
-- ============================================================================

BEGIN;

-- 1. District parsing from jofogas zipcode + URL
CREATE OR REPLACE FUNCTION parse_district_from_params(p_params JSONB, p_source_url TEXT)
RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE
AS $func$
DECLARE
    p JSONB;
    zip_str TEXT;
    zip_int INT;
    url_path TEXT;
    m TEXT[];
    roman TEXT;
    rn_val INT;
BEGIN
    -- zipcode: 1XYZ -> (XYZ/10)%100 (e.g. 1031 -> 3. ker, 1111 -> 11. ker)
    IF p_params IS NOT NULL AND jsonb_typeof(p_params) = 'array' THEN
        FOR p IN SELECT jsonb_array_elements(p_params) LOOP
            IF p->>'key' = 'zipcode'
               AND p->'values' IS NOT NULL
               AND jsonb_typeof(p->'values') = 'array'
               AND jsonb_array_length(p->'values') > 0
            THEN
                zip_str := p->'values'->0->>'value';
                zip_int := NULLIF(regexp_replace(COALESCE(zip_str, ''), '[^0-9]', '', 'g'), '')::INT;
                IF zip_int IS NOT NULL AND zip_int >= 1000 AND zip_int <= 1999 THEN
                    rn_val := (zip_int / 10) % 100;
                    IF rn_val BETWEEN 1 AND 23 THEN
                        RETURN rn_val || '. kerület';
                    END IF;
                END IF;
            END IF;
        END LOOP;
    END IF;

    -- URL path: numeric "11 ker" or "14.kerulet"
    url_path := lower(p_source_url);
    url_path := regexp_replace(url_path, '[_]', ' ', 'g');
    m := regexp_matches(url_path, '(\d+)\s*\.?\s*ker(?:ulet)?');
    IF m IS NOT NULL AND m[1]::INT BETWEEN 1 AND 23 THEN
        RETURN m[1] || '. kerület';
    END IF;

    -- URL path: roman numerals
    m := regexp_matches(url_path, '(x{0,3}(?:ix|iv|vi{0,3}|i{1,3}))\s*\.?\s*ker');
    IF m IS NOT NULL THEN
        roman := m[1];
        SELECT v.rn INTO rn_val FROM (VALUES
            ('i',1),('ii',2),('iii',3),('iv',4),('v',5),('vi',6),('vii',7),('viii',8),('ix',9),
            ('x',10),('xi',11),('xii',12),('xiii',13),('xiv',14),('xv',15),('xvi',16),
            ('xvii',17),('xviii',18),('xix',19),('xx',20),('xxi',21),('xxii',22),('xxiii',23)
        ) AS v(r, rn) WHERE v.r = roman;
        IF rn_val IS NOT NULL THEN
            RETURN rn_val || '. kerület';
        END IF;
    END IF;

    RETURN NULL;
END;
$func$;

-- 2. Views for Grafana
CREATE OR REPLACE VIEW v_field_coverage AS
SELECT
    source, COUNT(*) AS total,
    ROUND(COUNT(*) FILTER (WHERE price IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_price,
    ROUND(COUNT(*) FILTER (WHERE price_per_sqm IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_price_per_sqm,
    ROUND(COUNT(*) FILTER (WHERE area_sqm IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_area_sqm,
    ROUND(COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_rooms,
    ROUND(COUNT(*) FILTER (WHERE listing_type IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_listing_type,
    ROUND(COUNT(*) FILTER (WHERE property_type IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_property_type,
    ROUND(COUNT(*) FILTER (WHERE condition IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_condition,
    ROUND(COUNT(*) FILTER (WHERE heating IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_heating,
    ROUND(COUNT(*) FILTER (WHERE year_built IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_year_built,
    ROUND(COUNT(*) FILTER (WHERE floor IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_floor,
    ROUND(COUNT(*) FILTER (WHERE total_floors IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_total_floors,
    ROUND(COUNT(*) FILTER (WHERE balcony_sqm IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_balcony_sqm,
    ROUND(COUNT(*) FILTER (WHERE city IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_city,
    ROUND(COUNT(*) FILTER (WHERE lat IS NOT NULL AND lng IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_gps,
    ROUND(COUNT(*) FILTER (WHERE listed_at IS NOT NULL) * 100.0 / COUNT(*), 1) AS pct_listed_at
FROM listings WHERE is_active = true GROUP BY source ORDER BY source;

CREATE OR REPLACE VIEW v_listing_type_breakdown AS
SELECT listing_type, source, COUNT(*) AS cnt
FROM listings WHERE is_active = true AND listing_type IS NOT NULL
GROUP BY listing_type, source ORDER BY listing_type, source;

CREATE OR REPLACE VIEW v_property_type_breakdown AS
SELECT property_type, source, COUNT(*) AS cnt
FROM listings WHERE is_active = true AND property_type IS NOT NULL
GROUP BY property_type, source ORDER BY cnt DESC;

CREATE OR REPLACE VIEW v_city_listings AS
SELECT city, source, COUNT(*) AS cnt,
       ROUND(AVG(price)::NUMERIC, 0) AS avg_price,
       ROUND(AVG(price_per_sqm)::NUMERIC, 0) AS avg_price_per_sqm
FROM listings WHERE is_active = true AND city IS NOT NULL
GROUP BY city, source ORDER BY cnt DESC;

CREATE OR REPLACE VIEW v_price_stats AS
SELECT property_type, source, COUNT(*) AS cnt,
       ROUND(AVG(price)::NUMERIC, 0) AS avg_price,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price)::NUMERIC, 0) AS median_price,
       ROUND(MIN(price)::NUMERIC, 0) AS min_price,
       ROUND(MAX(price)::NUMERIC, 0) AS max_price,
       ROUND(AVG(price_per_sqm)::NUMERIC, 0) AS avg_price_per_sqm,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY price_per_sqm)::NUMERIC, 0) AS median_price_per_sqm
FROM listings WHERE is_active = true AND property_type IS NOT NULL AND price > 0
GROUP BY property_type, source ORDER BY property_type, source;

CREATE OR REPLACE VIEW v_daily_scrape_stats AS
SELECT DATE(scraped_at) AS scrape_date, source, COUNT(*) AS raw_entries
FROM raw_listings GROUP BY DATE(scraped_at), source ORDER BY scrape_date DESC;

CREATE OR REPLACE VIEW v_condition_breakdown AS
SELECT condition, source, COUNT(*) AS cnt
FROM listings WHERE is_active = true AND condition IS NOT NULL
GROUP BY condition, source ORDER BY cnt DESC;

CREATE OR REPLACE VIEW v_heating_breakdown AS
SELECT heating, source, COUNT(*) AS cnt
FROM listings WHERE is_active = true AND heating IS NOT NULL
GROUP BY heating, source ORDER BY cnt DESC;

COMMIT;
