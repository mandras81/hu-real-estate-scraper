#!/usr/bin/env python3
"""
Vault credential helper — dynamic PostgreSQL roles (GET-based).
Loads VAULT_ADDR / VAULT_TOKEN from ~/.openclaw/.env automatically.
Usage:
    from vault_creds import get_db_creds, make_pg_kwargs, make_dsn
    creds = get_db_creds("scraper-app")   # dynamic, 1h lease
    creds = get_db_creds_static("real-estate-scraper")  # static kv
"""

import json, os, sys, re
import urllib.request, urllib.error

# Auto-load from .env if vars aren't already set
_env_loaded = False
def _ensure_env():
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    if os.environ.get("VAULT_ADDR") and os.environ.get("VAULT_TOKEN"):
        return
    env_path = os.path.expanduser("~/.openclaw/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r'^(VAULT_ADDR|VAULT_TOKEN)\s*=\s*(.+)$', line)
                if m:
                    key, val = m.group(1), m.group(2).strip("'\"").strip()
                    os.environ.setdefault(key, val)

_ensure_env()

_VAULT_ADDR = os.environ.get("VAULT_ADDR", "http://10.10.10.106:8200")
_VAULT_TOKEN = os.environ.get("VAULT_TOKEN", "")

_DYNAMIC_ROLES = {
    "scraper-app": "real_estate_scraper",
    "upwork-app": "upwork_pipeline",
    "grafana-reader": "real_estate_scraper",
}

_STATIC_PATHS = {
    "real-estate-scraper": "secret/data/real-estate-scraper",
    "upwork-pipeline": "secret/data/upwork-pipeline",
}

_DYNAMIC_PATH_FMT = "postgresql/creds/{}"


def _vault_get(path):
    url = f"{_VAULT_ADDR}/v1/{path}"
    req = urllib.request.Request(url, headers={"X-Vault-Token": _VAULT_TOKEN})
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Vault API error {e.code} for {path}: "
            f"{e.read().decode(errors='replace')[:200]}"
        )
    except Exception as e:
        raise RuntimeError(f"Vault request failed for {path}: {e}")


def get_db_creds(role_name):
    """Get dynamic PostgreSQL credentials from Vault (GET-based)."""
    if role_name not in _DYNAMIC_ROLES:
        raise ValueError(f"Unknown dynamic role: {role_name}. Known: {list(_DYNAMIC_ROLES.keys())}")
    database = _DYNAMIC_ROLES[role_name]
    path = _DYNAMIC_PATH_FMT.format(role_name)
    data = _vault_get(path)
    creds = data["data"]
    return {
        "host": "10.10.10.103",
        "port": 5432,
        "database": database,
        "user": creds["username"],
        "password": creds["password"],
        "lease_duration": data.get("lease_duration", 3600),
    }


def get_db_creds_static(service_name):
    """Get static PostgreSQL credentials from Vault kv-v2."""
    path = _STATIC_PATHS.get(service_name)
    if not path:
        raise ValueError(f"Unknown static secret: {service_name}. Known: {list(_STATIC_PATHS.keys())}")
    data = _vault_get(path)["data"]["data"]
    db_map = {"real-estate-scraper": "real_estate_scraper", "upwork-pipeline": "upwork_pipeline"}
    return {
        "host": data.get("host", "10.10.10.103"),
        "port": int(data.get("port", 5432)),
        "database": data.get("database", db_map.get(service_name, "real_estate_scraper")),
        "user": data["user"],
        "password": data["password"],
    }


def get_creds(service_or_role):
    """Dynamic if available, else static."""
    if service_or_role in _DYNAMIC_ROLES:
        return get_db_creds(service_or_role)
    return get_db_creds_static(service_or_role)


def make_dsn(creds):
    import urllib.parse
    pw = urllib.parse.quote(creds["password"], safe="")
    return f"postgresql://{creds['user']}:{pw}@{creds['host']}:{creds['port']}/{creds['database']}"


def make_pg_kwargs(creds):
    return {
        "host": creds["host"], "port": creds["port"],
        "dbname": creds["database"],
        "user": creds["user"], "password": creds["password"],
        "client_encoding": "UTF8",
    }


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "scraper-app"
    try:
        creds = get_creds(role)
        print(f"Host: {creds['host']}:{creds['port']}")
        print(f"DB:   {creds['database']}")
        print(f"User: {creds['user']}")
        print(f"Pass: {creds['password'][:8]}...")
        if "lease_duration" in creds:
            print(f"TTL:  {creds['lease_duration']}s")
        import psycopg2
        conn = psycopg2.connect(**make_pg_kwargs(creds))
        cur = conn.cursor()
        cur.execute("SELECT current_user, current_database(), version()")
        u, d, v = cur.fetchone()
        print(f"\n✅ {u} @ {d}")
        cur.close(); conn.close()
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)
