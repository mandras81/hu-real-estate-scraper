"""
jofogas.hu/ingatlan — dumb collector v6
URL discovery: listing-page pagination sweep (/lakas, /haz, /garazs ?o=N).

Market structure (2026-06-25 confirmed):
  lakas  : 5,013 results, 201 pages @ 25/page
  haz    :   935 results,  38 pages @ 25/page
  garazs :   92 results,   4 pages @ 25/page
  Total  : ~6,040 listings

Delay strategy for 6K backfill (~3h):
  - Listing page sweep: 1.5-3s between pages  (243 pages ≈ 6-12 min)
  - Detail page scrape: 1-3s between listings (6K × 2s avg ≈ 3.3h)
"""

import json, re, sys, time, random
import requests

sys.path.insert(0, "/mnt/playground/workspace/workspace-data-engineering/projects/real-estate-scraper/src")
from db import get_conn

SESSION_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
# v6 delays: page sweep faster, listing scrape moderate
PAGE_DELAY_MIN, PAGE_DELAY_MAX = 1.5, 3.0
LISTING_DELAY_MIN, LISTING_DELAY_MAX = 1.0, 2.5

session = requests.Session()
session.headers.update(SESSION_HEADERS)

_listing_pages_cache = None


def discover_listing_pages():
    """Probe listing pages to discover pagination extent.
    Returns dict: {category: (max_page, result_count)}."""
    global _listing_pages_cache
    if _listing_pages_cache is not None:
        return _listing_pages_cache
    pages = {}
    for cat in ("lakas", "haz", "garazs"):
        try:
            r = session.get(f"https://ingatlan.jofogas.hu/{cat}", timeout=30)
            m = re.search(r'result_count:\s*(\d+)', r.text)
            count = int(m.group(1)) if m else 0
            max_p = max([int(p) for p in re.findall(r'(?<=\?o=)(\d+)', r.text)], default=1)
            pages[cat] = (max_p, count)
        except Exception as e:
            print(f"[jofogas] Warning: could not probe /{cat}: {e}")
            pages[cat] = (0, 0)
    _listing_pages_cache = pages
    return pages


def get_sitemap_info():
    """Return (1, total_listings) for pipeline logging compatibility."""
    pages = discover_listing_pages()
    total = sum(c for _, c in pages.values())
    return 1, total


def get_listing_urls(max_urls=None, cat_filter=None):
    """Sweep listing pages across /{lakas,haz,garazs}, return sorted unique listing URLs."""
    categories = [cat_filter] if cat_filter else ["lakas", "haz", "garazs"]
    pages_info = discover_listing_pages()

    all_urls = set()
    total_collected = 0

    for cat in categories:
        max_page, result_count = pages_info.get(cat, (0, 0))
        if max_page < 1:
            print(f"[jofogas] Skipping /{cat} (no pages)")
            continue

        print(f"[jofogas] /{cat}: ~{result_count} results, {max_page} pages")

        for page_num in range(1, max_page + 1):
            if max_urls and total_collected >= max_urls:
                break

            url = f"https://ingatlan.jofogas.hu/{cat}" if page_num == 1 else f"https://ingatlan.jofogas.hu/{cat}?o={page_num}"
            t0 = time.time()

            try:
                r = session.get(url, timeout=30)
                r.encoding = "utf-8"
            except Exception as e:
                print(f"  x page {page_num}: {e}")
                continue

            found = set(re.findall(r'href="(https://ingatlan\.jofogas\.hu[^"]*\.htm)"', r.text))
            new_urls = found - all_urls
            all_urls.update(new_urls)
            total_collected = len(all_urls)
            et = time.time() - t0

            print(f"  page {page_num}/{max_page}: +{len(new_urls)} new, {total_collected} total [{et:.1f}s]")

            if max_urls and total_collected >= max_urls:
                break

            # Page discovery delay (gentle — probing list pages, not individual ads)
            time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

        print(f"[jofogas] /{cat}: done — {total_collected} unique URLs so far")

    # Sort newest-first by ad ID at end of URL
    def ad_id(url):
        m = re.search(r'_(\d+)\.htm$', url)
        return int(m.group(1)) if m else 0
    sorted_urls = sorted(all_urls, key=ad_id, reverse=True)

    if max_urls:
        sorted_urls = sorted_urls[:max_urls]

    print(f"[jofogas] Total collected: {len(sorted_urls)} unique URLs")
    return sorted_urls


def extract_raw_data(html, url):
    """Extract ONLY __NEXT_DATA__ JSON + images from the page."""
    raw = {"product": {}, "lat": None, "lng": None, "images": []}
    lat = lng = None

    # 1. __NEXT_DATA__ JSON
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            nd = json.loads(m.group(1))
            product = None
            pp = nd.get("props", {}).get("pageProps", {})
            if pp:
                product = pp.get("product")
                if product and "geometry" in product:
                    coords = product["geometry"]
                    if isinstance(coords, dict):
                        lat = coords.get("latitude") or coords.get("lat")
                        lng = coords.get("longitude") or coords.get("lng")
            if not product:
                product = nd.get("product") or nd.get("listing")
            if product:
                raw["product"] = product
                if lat: raw["lat"] = lat
                if lng: raw["lng"] = lng
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 2. GPS fallback from HTML attributes
    if not raw.get("lat"):
        m2 = re.search(r'data-coordinate-lat="([^"]*)"', html)
        m3 = re.search(r'data-coordinate-lng="([^"]*)"', html)
        if m2: raw["lat"] = float(m2.group(1))
        if m3: raw["lng"] = float(m3.group(1))

    # 3. JSON-LD fallback
    m4 = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m4:
        try:
            raw["jsonld"] = json.loads(m4.group(1))
        except:
            pass

    return raw


def scrape_listing(url):
    try:
        resp = session.get(url, timeout=30)
        resp.encoding = "utf-8"
        return extract_raw_data(resp.text, url)
    except requests.RequestException as e:
        print(f"  x HTTP error: {e}")
        return None



def get_existing_urls():
    """Return set of source_urls already in raw_listings for jofogas."""
    from db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT source_url FROM raw_listings WHERE source='jofogas'")
    urls = set(r[0] for r in cur.fetchall())
    cur.close(); conn.close()
    return urls


def get_new_urls(max_urls=None, cat_filter=None):
    """Discover listing URLs, filter to only unseen ones, return sorted."""
    all_urls = get_listing_urls(max_urls=None, cat_filter=cat_filter)
    existing = get_existing_urls()
    new_urls = [u for u in all_urls if u not in existing]
    print('[jofogas] incremental: %d total, %d new, %d existing' % (len(all_urls), len(new_urls), len(existing)))
    if max_urls:
        new_urls = new_urls[:max_urls]
    return new_urls

def main(max_listings=None):
    print(f"{'='*60}")
    print("JOFOGAS v6 — listing-page sweep (replaces broken sitemap)")
    print(f"{'='*60}\n")
    print(f"Delays: page_sweep={PAGE_DELAY_MIN}-{PAGE_DELAY_MAX}s, listing={LISTING_DELAY_MIN}-{LISTING_DELAY_MAX}s\n")

    print("[jofogas] Discovering listing pages...")
    listing_urls = get_listing_urls(max_urls=max_listings)

    if not listing_urls:
        print("[jofogas] No URLs found. Exiting.")
        return 0

    print(f"[jofogas] Starting scrape of {len(listing_urls)} URLs\n")

    conn = get_conn()
    cur = conn.cursor()
    scraped = inserted = skipped = 0
    t_start = time.time()

    for i, url in enumerate(listing_urls, 1):
        t0 = time.time()
        print(f"[{i}/{len(listing_urls)}] ...{url[-50:]}")

        raw_data = scrape_listing(url)
        if not raw_data:
            skipped += 1
            print("  x failed\n")
            continue

        scraped += 1
        raw_json = json.dumps(raw_data, ensure_ascii=False)

        try:
            cur.execute(
                "INSERT INTO raw_listings (source, source_url, raw_data) VALUES (%s, %s, %s::jsonb) ON CONFLICT (source_url) DO UPDATE SET raw_data = EXCLUDED.raw_data, scraped_at = NOW();",
                ("jofogas", url, raw_json)
            )
            conn.commit()
            inserted += 1
        except Exception as e:
            conn.rollback()
            skipped += 1
            print(f"  x DB error: {e}")
            continue

        subject = raw_data.get("product", {}).get("subject", "?")
        price = raw_data.get("product", {}).get("price", "?")
        et = time.time() - t0
        print(f"  + {str(subject)[:40]} | {price} | {et:.1f}s")
        time.sleep(random.uniform(LISTING_DELAY_MIN, LISTING_DELAY_MAX))

    et = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"DONE: {scraped} scraped, {inserted} inserted/updated, {skipped} skipped")
    print(f"Time: {et:.0f}s ({et/max(scraped,1):.1f}s avg)")
    print(f"{'='*60}")

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    inc = "--incremental" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    n = int(args[0]) if args else None
    main(n, incremental=inc)
