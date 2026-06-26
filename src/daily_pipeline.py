#!/usr/bin/env python3
"""
Daily pipeline runner: scrape → refresh_listings() → refresh_consolidation()
Run from project root: python3 src/daily_pipeline.py [count_per_source]
Uses Vault dynamic credentials (scraper-app role) for all DB connections.
"""

import sys, time, subprocess, os, re
from datetime import datetime, timezone
from vault_creds import get_db_creds, make_pg_kwargs, make_dsn

PROJECT = "/mnt/playground/workspace/workspace-data-engineering/projects/real-estate-scraper"
os.chdir(PROJECT)
COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 1000

# Get Vault dynamic creds once at startup
_CREDS = get_db_creds("scraper-app")


def run(label, cmd, timeout=1800):
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"[{label}] Starting...")
    sys.stdout.flush()
    rc = subprocess.call(cmd, shell=True, timeout=timeout)
    et = time.time() - t0
    print(f"[{label}] {'OK' if rc == 0 else 'FAILED (exit %d)' % rc} — {et:.0f}s")
    sys.stdout.flush()
    return rc == 0, et


def get_conn():
    import psycopg2
    return psycopg2.connect(**make_pg_kwargs(_CREDS))


def run_sql(sql):
    import psycopg2
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()
    t0 = time.time()
    cur.execute(sql)
    try:
        result = cur.fetchone()
        val = result[0] if result else None
    except Exception:
        val = None
    et = time.time() - t0
    conn.close()
    return val, et


def log_run(run_id, **kwargs):
    if not run_id:
        return
    try:
        conn = get_conn()
        cur = conn.cursor()
        sets = ", ".join([f"{k}=%s" for k in kwargs])
        cur.execute(f"UPDATE pipeline_runs SET {sets} WHERE id=%s",
                    list(kwargs.values()) + [run_id])
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[pipeline_runs] Warning: {e}")


def discover_jofogas_market():
    sys.path.insert(0, f"{PROJECT}/src")
    import scrape_jofogas as jf
    pages, per_page = jf.get_sitemap_info()
    print(f"[inventory] jofogas: ~{per_page} visible in sitemap (total unknown)")
    return None


def discover_otthonterkep_market():
    import requests, lxml.etree as ET
    NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
    from scrape_otthonterkep import session as otto_session
    total = 0
    for part in [1, 2, 3]:
        r = otto_session.get(f"https://new.ingatlantajolo.hu/sitemap/sitemap_part_{part}.xml", timeout=60)
        root = ET.fromstring(r.content)
        for loc in root.iter(f"{{{NS}}}loc"):
            if "/ingatlan/" in loc.text.strip():
                total += 1
    print(f"[inventory] otthonterkep: {total}")
    return total


def check_missed_morning_run():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM pipeline_runs
            WHERE status = 'success'
              AND run_start >= date_trunc('day', NOW() AT TIME ZONE 'Europe/Budapest')::timestamptz
        """)
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count == 0
    except Exception as e:
        print(f"[catchup] Check failed: {e}")
        return False


def main():
    is_catchup = check_missed_morning_run()
    print(f"=== Daily Pipeline === {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Count per source: {COUNT}")
    print(f"Catch-up mode: {'YES' if is_catchup else 'NO'}")
    start = time.time()

    run_id = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO pipeline_runs (run_start, status, count_per_source) VALUES (NOW(), 'running', %s) RETURNING id",
            (COUNT,))
        run_id = cur.fetchone()[0]
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        print(f"[pipeline_runs] Warning: could not create record: {e}")

    jofogas_before = run_sql("SELECT count(*) FROM raw_listings WHERE source='jofogas'")[0] or 0
    otthon_before = run_sql("SELECT count(*) FROM raw_listings WHERE source='otthonterkep'")[0] or 0
    listings_before = run_sql("SELECT count(*) FROM listings")[0] or 0

    # Step 1+2: scrape
    jf_ok, jf_dur = run("jofogas scrape", f"python3 src/scrape_jofogas.py --incremental {COUNT}")
    ot_ok, ot_dur = run("otthonterkep scrape", f"python3 src/scrape_otthonterkep.py --incremental {COUNT}")
    ok = jf_ok and ot_ok

    # Step 3: refresh_listings
    print(f"\n{'='*60}\n[refresh_listings] Parsing raw→listings...")
    sys.stdout.flush()
    _, parse_et = run_sql("SELECT refresh_listings();")
    print(f"[refresh_listings] Done ({parse_et:.2f}s)")
    sys.stdout.flush()

    # Step 4: refresh_consolidation
    print(f"\n{'='*60}\n[refresh_consolidation] Running consolidation...")
    sys.stdout.flush()
    _, cons_et = run_sql("SELECT refresh_consolidation();")
    print(f"[refresh_consolidation] Done ({cons_et:.2f}s)")
    sys.stdout.flush()

    total_elapsed = time.time() - start

    jofogas_after = run_sql("SELECT count(*) FROM raw_listings WHERE source='jofogas'")[0] or 0
    otthon_after = run_sql("SELECT count(*) FROM raw_listings WHERE source='otthonterkep'")[0] or 0
    listings_after = run_sql("SELECT count(*) FROM listings")[0] or 0
    jofogas_listings = run_sql("SELECT count(*) FROM listings WHERE source='jofogas'")[0] or 0
    otthon_listings = run_sql("SELECT count(*) FROM listings WHERE source='otthonterkep'")[0] or 0

    try:
        jofogas_market = discover_jofogas_market()
    except Exception as e:
        print(f"[inventory] jofogas failed: {e}")
        jofogas_market = None
    try:
        otthon_market = discover_otthonterkep_market()
    except Exception as e:
        print(f"[inventory] otthonterkep failed: {e}")
        otthon_market = None

    otthon_market_val = otthon_market or 0
    otthon_coverage = round(otthon_after / otthon_market_val * 100, 1) if otthon_market_val else None

    log_run(run_id,
            run_end=datetime.now(timezone.utc),
            status="success" if ok else "failed",
            count_per_source=COUNT,
            jofogas_new=jofogas_after - jofogas_before,
            otthonterkep_new=otthon_after - otthon_before,
            jofogas_total=jofogas_after,
            otthonterkep_total=otthon_after,
            jofogas_count=jofogas_listings,
            otthonterkep_count=otthon_listings,
            listings_after=listings_after,
            jofogas_market_total=jofogas_market,
            otthonterkep_market_total=otthon_market,
            jofogas_raw_after=jofogas_after,
            otthonterkep_raw_after=otthon_after,
            coverage_pct=otthon_coverage,
            total_duration_ms=int(total_elapsed * 1000))

    print(f"\n{'='*60}")
    print(f"Pipeline {'✅ COMPLETE' if ok else '⚠️  PARTIAL'} — {total_elapsed:.0f}s total")
    print(f"  jofogas:  {jofogas_after}/{jofogas_market or '?'} raw ({jofogas_listings} parsed)")
    print(f"  otthonterkep:  {otthon_after}/{otthon_market or '?'} raw ({otthon_listings} parsed)")
    print(f"  otthonterkep coverage: {otthon_coverage}%")
    print(f"{'='*60}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
