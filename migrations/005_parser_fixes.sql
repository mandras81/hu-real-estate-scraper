-- ============================================================================
-- Migration 005: Parser fixes for parse_otthonterkep
-- 
-- Changes:
-- 1. Belső szintek -> total_floors (was incorrectly mapped to floor)
-- 2. TERÜLET -> plot_sqm (was incorrectly mapped to area_sqm)
-- 3. area_sqm sanity cap 5-5000 m² (reject plot-sized values)
-- 4. price_per_sqm guard (< 10M HUF/sqm) to avoid overflow
-- 5. Removed fallback_price (catches bogus numbers from HTML)
-- 6. Widened columns: price_per_sqm NUMERIC(12,1), area_sqm NUMERIC(10,1),
--    plot_sqm NUMERIC(12,1) to handle real-world values
-- ============================================================================

BEGIN;

-- Drop dependent views first
DROP VIEW IF EXISTS v_city_listings CASCADE;
DROP VIEW IF EXISTS v_field_coverage CASCADE;
DROP VIEW IF EXISTS v_price_stats CASCADE;
DROP VIEW IF EXISTS v_condition_breakdown CASCADE;
DROP VIEW IF EXISTS v_heating_breakdown CASCADE;
DROP VIEW IF EXISTS v_listing_type_breakdown CASCADE;
DROP VIEW IF EXISTS v_property_type_breakdown CASCADE;
DROP VIEW IF EXISTS v_daily_scrape_stats CASCADE;
DROP VIEW IF EXISTS v_cities_needing_geocode CASCADE;
DROP VIEW IF EXISTS v_properties_enriched CASCADE;

-- Widen numeric columns to handle real estate values
ALTER TABLE listings ALTER COLUMN price_per_sqm TYPE NUMERIC(12,1);
ALTER TABLE listings ALTER COLUMN area_sqm TYPE NUMERIC(10,1);
ALTER TABLE listings ALTER COLUMN plot_sqm TYPE NUMERIC(12,1);

-- Update parse_otthonterkep function
DROP FUNCTION IF EXISTS parse_otthonterkep(jsonb, text) CASCADE;

-- Note: the actual CREATE OR REPLACE FUNCTION is applied via
-- python src/migrate_005.py using the current function body from the DB
-- See also the inline _fix scripts in git history

-- Recreate analytics views (migration 004)
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

-- (other views recreated by migrate script)
COMMIT;
