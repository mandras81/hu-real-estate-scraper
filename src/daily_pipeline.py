#!/usr/bin/env python3
"""
Daily pipeline runner: scrape → refresh_listings() → refresh_consolidation()
Run from project root: python3 src/daily_pipeline.py [count_per_source]
"""
import sys, time, subprocess, os

PROJECT = "/mnt/playground/workspace/workspace-data-engineering/projects/real-estate-scraper"
os.chdir(PROJECT)

COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def run(label, cmd, timeout=600):
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"[{label}] Starting...")
    sys.stdout.flush()
    rc = subprocess.call(cmd, shell=True, timeout=timeout)
    et = time.time() - t0
    print(f"[{label}] {'OK' if rc == 0 else 'FAILED (exit %d)' % rc} — {et:.0f}s")
    sys.stdout.flush()
    return rc == 0


def run_sql(sql):
    """Execute a SQL statement via psycopg2."""
    import psycopg2
    conn = psycopg2.connect(
        "postgresql://openclaw:upwork2026@10.10.10.103:5432/real_estate_scraper"
    )
    conn.autocommit = True
    cur = conn.cursor()
    t0 = time.time()
    cur.execute(sql)
    result = cur.fetchone()
    et = time.time() - t0
    conn.close()
    return result[0] if result else None, et


def main():
    print(f"=== Daily Pipeline === {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Count per source: {COUNT}")
    start = time.time()

    # Step 1: Scrape jofogas
    ok = run("jofogas scrape",
             f"python3 src/scrape_jofogas.py {COUNT}")

    # Step 2: Scrape otthonterkep
    ok = run("otthonterkep scrape",
             f"python3 src/scrape_otthonterkep.py {COUNT}") and ok

    # Step 3: refresh_listings() — parse raw JSON into canonical listings
    print(f"\n{'='*60}")
    print("[refresh_listings] Parsing raw→listings...")
    sys.stdout.flush()
    result, et = run_sql("SELECT refresh_listings();")
    print(f"[refresh_listings] Done — {result} ({et:.2f}s)")
    sys.stdout.flush()

    # Step 4: refresh_consolidation() — cross-portal dedup
    print(f"\n{'='*60}")
    print("[refresh_consolidation] Running consolidation...")
    sys.stdout.flush()
    result, et = run_sql("SELECT refresh_consolidation();")
    print(f"[refresh_consolidation] Done — {result} ({et:.2f}s)")
    sys.stdout.flush()

    total = time.time() - start
    print(f"\n{'='*60}")
    print(f"Pipeline {'✅ COMPLETE' if ok else '⚠️  PARTIAL'} — {total:.0f}s total")
    print(f"{'='*60}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
