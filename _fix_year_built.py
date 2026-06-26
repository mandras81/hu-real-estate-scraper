#!/usr/bin/env python3
"""Fix parse_jofogas: building_date uses label, jfg_area added to area keys."""
import psycopg2

conn = psycopg2.connect(
    host="10.10.10.103", port=5432,
    dbname="real_estate_scraper",
    user="openclaw", password="***"
)
cur = conn.cursor()

cur.execute("SELECT prosrc FROM pg_proc WHERE proname = 'parse_jofogas'")
body = cur.fetchone()[0]

old = "WHEN 'year_built', 'build_year', 'building_date' THEN year_built := NULLIF(regexp_replace(pval, '[^0-9]', '', 'g'), '')::INT;"
new = "WHEN 'year_built', 'build_year' THEN year_built := NULLIF(regexp_replace(pval, '[^0-9]', '', 'g'), '')::INT; WHEN 'building_date' THEN year_built := NULLIF(regexp_replace(COALESCE(pvals->0->>'label', pval, ''), '[^0-9]', '', 'g'), '')::INT;"

if old not in body:
    print("Old snippet not found! Exit.")
    conn.close()
    exit(1)
body = body.replace(old, new)

# jfg_area -> area_sqm
old2 = "WHEN 'size', 'area', 'built_size' THEN"
new2 = "WHEN 'size', 'area', 'built_size', 'jfg_area' THEN"
body = body.replace(old2, new2)

cur.execute("DROP FUNCTION IF EXISTS parse_jofogas(raw_data jsonb, source_url text) CASCADE")

full_sql = f"""CREATE OR REPLACE FUNCTION public.parse_jofogas(raw_data jsonb, source_url text)
 RETURNS TABLE(source text, title text, price integer, price_per_sqm integer, currency text, property_type text, listing_type text, location_raw text, city text, district text, lat numeric, lng numeric, area_sqm numeric, plot_sqm numeric, rooms text, floor integer, total_floors integer, condition text, heating text, year_built integer, balcony_sqm numeric, description text, image_urls text[], seller_type text, listed_at timestamp with time zone, is_active boolean, checksum text, raw_data_out jsonb)
 LANGUAGE plpgsql
 IMMUTABLE
 AS $$""" + body + "\n$$"

cur.execute(full_sql)
conn.commit()
print("Done: building_date fixed + jfg_area added")

# Verify
cur.execute("""
    SELECT r.source_url FROM raw_listings r
    WHERE r.source = 'jofogas'
    AND r.raw_data->'product'->'parameters' @> '[{"key":"building_date"}]'::jsonb
    LIMIT 1
""")
url = cur.fetchone()[0]
cur.execute("SELECT year_built, price, area_sqm, city FROM parse_jofogas((SELECT raw_data FROM raw_listings WHERE source_url = %s), %s)", (url, url))
row = cur.fetchone()
print(f"Test parse: year_built={row[0]} (should be 2012-2026), price={row[1]}, area_sqm={row[2]}, city={row[3]}")

# Apply via refresh
cur.execute("SELECT refresh_listings()")
print(f"Refresh: {cur.fetchone()[0]} rows")

cur.execute("""
    SELECT source,
           COUNT(*) FILTER (WHERE year_built IS NOT NULL) * 100.0 / COUNT(*)
    FROM listings WHERE is_active = true GROUP BY source
""")
for r in cur.fetchall():
    print(f"  year_built {r[0]}: {r[1]:.1f}%")

cur.execute("""
    SELECT source,
           COUNT(*) FILTER (WHERE area_sqm IS NOT NULL) * 100.0 / COUNT(*)
    FROM listings WHERE is_active = true GROUP BY source
""")
for r in cur.fetchall():
    print(f"  area_sqm {r[0]}: {r[1]:.1f}%")

conn.close()
