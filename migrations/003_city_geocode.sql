-- 003_city_geocode.sql
-- Applies city-level geocoding fallback & jofogas HU→EN property_type mapping
-- Applied: 2026-06-24

-- === Part 1: City Coordinates Table ===
CREATE TABLE IF NOT EXISTS city_coordinates (
    id              SERIAL PRIMARY KEY,
    city            TEXT NOT NULL UNIQUE,
    lat             NUMERIC NOT NULL,
    lng             NUMERIC NOT NULL,
    display_name    TEXT,
    geocoded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_city_coordinates_city ON city_coordinates (city);

-- === Part 2: parse_otthonterkep() GPS fallback ===
-- Injected: IF lat IS NULL AND city ... SELECT FROM city_coordinates ... Budapest centroid

-- === Part 3: parse_jofogas() HU→EN property_type mapping ===
-- tégla,panel → apartment | ház → house | telek → land | garázs → parking
-- üzlet,iroda → commercial | szoba → room | egyéb → other

-- === Part 4: find_property_matches() tiered scoring ===
-- score 0.9: area ±15% + exact rooms | 0.5: area ±15% | 0.3: area ±30%

-- === Part 5: auto_confirm_matches() tiered thresholds ===
-- det>=0.9 AND text>=0.2 | det>=0.5 AND text>=0.5 | det>=0.3 AND text>=0.7

-- === Part 6: View ===
CREATE OR REPLACE VIEW v_cities_needing_geocode AS
SELECT DISTINCT l.city, COUNT(*) AS listing_count
FROM listings l
WHERE l.source = 'otthonterkep'
  AND (l.lat IS NULL OR l.lng IS NULL)
  AND l.city IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM city_coordinates cc WHERE cc.city = l.city)
GROUP BY l.city ORDER BY COUNT(*) DESC;
