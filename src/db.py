"""Database layer: minimal helpers. No business logic."""
import re
import psycopg2

DB_URL = "postgresql://openclaw:upwork2026@10.10.10.103:5432/real_estate_scraper"


def get_conn():
    conn = psycopg2.connect(DB_URL)
    conn.set_client_encoding("UTF8")
    conn.autocommit = False
    return conn


def clean_int(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    m = re.search(r'\d+', str(val).replace(" ", ""))
    return int(m.group(0)) if m else None


def clean_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r'[\d.]+', str(val).replace(",", ".").replace(" ", ""))
    return float(m.group(0)) if m else None


def clean_text(val):
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None
