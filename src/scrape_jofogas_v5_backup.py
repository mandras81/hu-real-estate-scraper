"""
jofogas.hu/ingatlan — dumb collector v5
Fetches HTML, extracts __NEXT_DATA__ JSON, dumps to raw_listings.
Zero business logic. All parsing happens in SQL (parse_jofogas).
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
DELAY_MIN, DELAY_MAX = 2, 5

session = requests.Session()
session.headers.update(SESSION_HEADERS)


def discover_sitemap_pages():
    """Jofogas sitemap ignores the ?o= parameter — returns same ~96 ingatlan URLs regardless of offset.
    We only need one page. The sitemap only reveals ~96 active listings at any time."""
    base = "https://www.jofogas.hu/sitemap.xml"
    print('[jofogas] Using single sitemap page (%s)' % base)
    return [base]


SITEMAP_PAGES = None


def get_sitemap_info():
    global SITEMAP_PAGES
    if SITEMAP_PAGES is None:
        SITEMAP_PAGES = discover_sitemap_pages()
    # Sitemap only exposes one page with ~96 ingatlan URLs (o parameter is ignored)
    # Total market size is unknown — we track unique URLs collected over time instead
    ingatlan_visible = 96
    return 1, ingatlan_visible


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get_listing_urls(max_urls=100):
    urls = []
    global SITEMAP_PAGES
    if SITEMAP_PAGES is None:
        SITEMAP_PAGES = discover_sitemap_pages()
    for sm_url in SITEMAP_PAGES:
        print("[jofogas] Sitemap ...%s" % sm_url[-20:])
        try:
            r = session.get(sm_url, timeout=30)
        except Exception as e:
            print("  x HTTP: %s" % e)
            continue
        found = re.findall(r'https://ingatlan\.jofogas\.hu[^<]*\.htm', r.text)
        urls.extend(found)
        print("  %d URLs, %d total" % (len(found), len(urls)))
        if len(urls) >= max_urls:
            break
    return urls[:max_urls]


def extract_raw_data(html, url):
    """Extract ONLY __NEXT_DATA__ JSON + images from the page."""
    raw = {"product": {}, "lat": None, "lng": None, "images": []}

    # 1. __NEXT_DATA__ JSON
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            nd = json.loads(m.group(1))
            product = None
            pp = nd.get("props", {}).get("pageProps", {})
            if pp:
                product = pp.get("product")
                # GPS from product geometry
                if product and "geometry" in product:
                    coords = product["geometry"]
                    if isinstance(coords, dict):
                        raw["lat"] = coords.get("latitude") or coords.get("lat")
                        raw["lng"] = coords.get("longitude") or coords.get("lng")
            # Fallback: check top-level or other keys
            if not product:
                product = nd.get("product") or nd.get("listing")
            if product:
                raw["product"] = product
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # 2. GPS fallback: try __NEXT_DATA__ pageProps.parameters
    if not raw["lat"] and not raw["lat"]:
        m2 = re.search(r'data-coordinate-lat="([^"]*)"', html)
        m3 = re.search(r'data-coordinate-lng="([^"]*)"', html)
        if m2: raw["lat"] = float(m2.group(1))
        if m3: raw["lng"] = float(m3.group(1))

    # 3. JSON-LD fallback (for fields not in __NEXT_DATA__)
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


def main(max_listings=50):
    print(f"{'='*60}")
    print("JOFOGAS v5 — dumb collector (raw JSON only)")
    print(f"{'='*60}\n")
    print("[jofogas] Fetching sitemap URLs...")
    listing_urls = get_listing_urls(max_listings)
    print(f"[jofogas] Got {len(listing_urls)} listing URLs\n")

    conn = get_conn()
    cur = conn.cursor()
    scraped = inserted = 0
    t_start = time.time()

    for i, url in enumerate(listing_urls, 1):
        t0 = time.time()
        print(f"[{i}/{max_listings}] ...{url[-40:]}")
        raw_data = scrape_listing(url)
        if not raw_data:
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
            print(f"  x DB error: {e}")
            continue

        subject = raw_data.get("product", {}).get("subject", "?")
        price = raw_data.get("product", {}).get("price", "?")
        et = time.time() - t0
        print(f"  + {subject[:40]} | {price} Ft | {et:.1f}s")
        polite_delay()

    et = time.time() - t_start
    print(f"\n{'='*60}")
    print(f"DONE: {scraped} scraped, {inserted} inserted/updated")
    print(f"Time: {et:.0f}s ({et/max(scraped,1):.1f}s avg)")
    print(f"{'='*60}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(n)
