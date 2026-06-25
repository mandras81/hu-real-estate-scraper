"""Database layer: minimal helpers. No business logic."""
import re
import psycopg2
from vault_creds import get_db_creds, make_pg_kwargs

# Dynamic credentials — fresh lease per process startup
_CREDS = get_db_creds("scraper-app")


def get_conn():
    conn = psycopg2.connect(**make_pg_kwargs(_CREDS))
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
