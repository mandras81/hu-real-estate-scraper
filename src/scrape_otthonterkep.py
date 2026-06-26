"""
otthonterkep.hu — dumb collector v5
Fetches HTML, extracts raw JSON payloads, dumps to raw_listings.
Zero business logic. All parsing happens in SQL (parse_otthonterkep).
"""

import json, re, sys, time, random
import lxml.etree as ET
import requests
from db import get_conn, clean_text

DELAY_MIN, DELAY_MAX = 0.5, 1.5
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAPS = [
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_1.xml",
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_2.xml",
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_3.xml",
]

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/149.0.0.0", "Accept-Language": "hu-HU,hu;q=0.9"})


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get_listing_urls(max_urls=100):
    urls = []
    for sm in SITEMAPS:
        print(f"[otto] Sitemap ...{sm[-20:]}")
        resp = session.get(sm, timeout=60)
        root = ET.fromstring(resp.content)
        for loc in root.iter(f"{{{NS}}}loc"):
            url = loc.text.strip()
            if url and "/ingatlan/" in url:
                urls.append(url)
        if max_urls and len(urls) >= max_urls:
            break
    return urls[:max_urls] if max_urls else urls


def extract_raw_data(html, url):
    """Extract ONLY raw JSON payloads from the page. No parsing, no logic."""
    raw = {"page_data": {}, "bootstrap_grid": {}, "property_summary": {}, "jsonld": {}, "images": [], "lat": None, "lng": None, "seller_h2": None}

    # 1. page_data JSON (inline <script> with uid/url keys)
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        s = m.group(1).strip()
        if not s: continue
        try:
            d = json.loads(s)
            if isinstance(d, dict) and "uid" in d and "url" in d:
                raw["page_data"] = d
                break
        except:
            pass

    # 2. JSON-LD (for price/name/description)
    m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if m:
        try:
            raw["jsonld"] = json.loads(m.group(1))
        except:
            pass

    # 3. Bootstrap grid (summary boxes)
    details = {}
    for vh, lb in re.findall(r'<h5[^>]*class="fw-bolder[^"]*"[^>]*>\s*(.*?)\s*</h5>\s*<small[^>]*class="[^"]*summary-data-box[^"]*"[^>]*>\s*(.*?)\s*</small>', html, re.DOTALL):
        vc = re.sub(r'<[^>]+>', '', vh).strip()
        vc = re.sub(r'\s+', ' ', vc).strip()
        vc = re.sub(r'\s*m2?\s*$', '', vc, flags=re.IGNORECASE).strip()
        lc = re.sub(r'<[^>]+>', '', lb).strip()
        if lc and vc:
            details[lc] = vc
    raw["bootstrap_grid"] = details

    # 4. Property summary (extra detail rows)
    items = {}
    for lbl, val in re.findall(r'<span[^>]*class="property-summary__label"[^>]*>\s*(.*?)\s*</span>\s*<span[^>]*class="property-summary__data[^"]*"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL):
        lc = re.sub(r'<[^>]+>', '', lbl).strip()
        vc = re.sub(r'<[^>]+>', '', val).strip()
        vc = re.sub(r'\s+', ' ', vc).strip()
        if lc and vc:
            items[lc] = vc
    raw["property_summary"] = items

    # 5. Seller name from <h2>
    sm = re.search(r'<h2[^>]*class="text-dark[^"]*"[^>]*>\s*(.*?)\s*</h2>', html)
    if not sm:
        sm = re.search(r'<h2[^>]*>(.*?)</h2>', html)
    if sm:
        raw["seller_h2"] = clean_text(clean_text(re.sub(r'<[^>]+>', '', sm.group(1))))

    # 6. Page title from <title>
    ptm = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
    if ptm:
        raw["page_title"] = re.sub(r'<[^>]+>', '', ptm.group(1)).strip()

    # 7. Images
    imgs = []
    seen = set()
    for m in re.finditer(r'(https?://images\d*\.ingatlantajolo\.hu/[^"\']*)', html):
        src = m.group(1)
        if "/ad_" in src and "/noimage" not in src and src not in seen:
            seen.add(src)
            imgs.append(src)
    raw["images"] = imgs

    # 7. GPS from data-lat/data-lng
    m = re.search(r'data-lat="([\d.-]+)"', html)
    n = re.search(r'data-lng="([\d.-]+)"', html)
    if m and n:
        raw["lat"] = float(m.group(1))
        raw["lng"] = float(n.group(1))

    # 8. Fallback price from <title> or regex
    pm = re.search(r'(\d[\d\s]*\d)\s*Ft', html)
    if pm:
        raw["fallback_price"] = int(re.sub(r'\s', '', pm.group(1)))

    return raw


def scrape_listing(url):
    try:
        resp = session.get(url, timeout=30)
        resp.encoding = "utf-8"
        raw_data = extract_raw_data(resp.text, url)
        return raw_data
    except requests.RequestException as e:
        print(f"  x HTTP error: {e}")
        return None



def get_existing_urls():
    """Return set of source_urls already in raw_listings for otthonterkep."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT source_url FROM raw_listings WHERE source='otthonterkep'")
    urls = set(r[0] for r in cur.fetchall())
    cur.close(); conn.close()
    return urls


def get_new_urls(max_urls=None):
    """Discover all sitemap URLs, filter to unseen, return sorted."""
    all_urls = get_listing_urls(max_urls=None)
    existing = get_existing_urls()
    new_urls = [u for u in all_urls if u not in existing]
    print(f'[otto] incremental: {len(all_urls)} total, {len(new_urls)} new, {len(existing)} existing')
    if max_urls:
        new_urls = new_urls[:max_urls]
    return new_urls

def main(max_listings=50, incremental=False):
    print(f"{'='*60}")
    print("OTTHONTERKEP v5 — dumb collector (raw JSON only)")
    print(f"{'='*60}\n")
    print("[otto] Fetching sitemap URLs...")
    listing_urls = get_listing_urls(max_listings)
    print(f"[otto] Got {len(listing_urls)} listing URLs\n")

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
                ("otthonterkep", url, raw_json)
            )
            conn.commit()
            inserted += 1
        except Exception as e:
            conn.rollback()
            print(f"  x DB error: {e}")
            continue

        city = raw_data.get("page_data", {}).get("city", "?")
        price = raw_data.get("page_data", {}).get("price", "?")
        img_count = len(raw_data.get("images", []))
        et = time.time() - t0
        print(f"  + [{city}] {price} Ft | {img_count}img | {et:.1f}s")
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
