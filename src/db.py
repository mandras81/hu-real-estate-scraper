"""Database connection for real_estate_scraper POC (UTF8 DB)."""

import hashlib
import json
import psycopg2

DB_URL = "postgresql://openclaw:upwork2026@10.10.10.103:5432/real_estate_scraper"


def get_conn():
    conn = psycopg2.connect(DB_URL)
    conn.set_client_encoding("UTF8")
    conn.autocommit = False
    return conn


def compute_checksum(d: dict) -> str:
    raw = f"{d.get('price')}|{d.get('area_sqm')}|{d.get('lat')}|{d.get('lng')}|{d.get('rooms')}|{d.get('city')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def upsert_listing(conn, record: dict) -> bool:
    cur = conn.cursor()
    sql = """
        INSERT INTO listings (
            source, source_url, title, price, price_per_sqm, currency,
            property_type, listing_type, location_raw, city, district,
            lat, lng, area_sqm, plot_sqm, rooms, floor, total_floors,
            condition, heating, year_built, balcony_sqm, description,
            image_urls, seller_type, seller_name, listed_at,
            scraped_at, is_active, checksum, raw_data
        ) VALUES (
            %(source)s, %(source_url)s, %(title)s, %(price)s, %(price_per_sqm)s, %(currency)s,
            %(property_type)s, %(listing_type)s, %(location_raw)s, %(city)s, %(district)s,
            %(lat)s, %(lng)s, %(area_sqm)s, %(plot_sqm)s, %(rooms)s, %(floor)s, %(total_floors)s,
            %(condition)s, %(heating)s, %(year_built)s, %(balcony_sqm)s, %(description)s,
            %(image_urls)s, %(seller_type)s, %(seller_name)s, %(listed_at)s,
            NOW(), TRUE, %(checksum)s, %(raw_data)s
        )
        ON CONFLICT (source_url) DO UPDATE SET
            price         = EXCLUDED.price,
            price_per_sqm = EXCLUDED.price_per_sqm,
            is_active     = TRUE,
            scraped_at    = NOW(),
            checksum      = EXCLUDED.checksum,
            raw_data      = EXCLUDED.raw_data
    """
    try:
        cur.execute(sql, record)
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        print(f"  DB error: {e}")
        return False
    finally:
        cur.close()


def clean_int(val):
    if val is None: return None
    try: return int(val)
    except (ValueError, TypeError): return None

def clean_float(val):
    if val is None: return None
    try: return float(val)
    except (ValueError, TypeError): return None

def clean_text(val):
    if val is None: return None
    s = str(val).strip()
    return s if s else None
