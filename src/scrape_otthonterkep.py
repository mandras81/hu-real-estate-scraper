"""
otthonterkep.hu production scraper v4 (HTTP-first, no browser needed)
Strategy: Sitemap crawl -> requests -> Nominatim GPS -> PostgreSQL
SSR HTML has: area, rooms, heating, year_built, condition, images, energy, seller.
v4: HTTP-only (~0.5s/page vs 8s/page with Playwright), GPS via Nominatim API.
"""

import json, re, sys, time, random
import lxml.etree as ET
import requests
from db import get_conn, upsert_listing, compute_checksum, clean_int, clean_float, clean_text

DELAY_MIN, DELAY_MAX = 0.5, 1.5
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
SITEMAPS = [
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_1.xml",
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_2.xml",
    "https://new.ingatlantajolo.hu/sitemap/sitemap_part_3.xml",
]

PROPERTY_TYPE_MAP = {
    "haz-hazresz": "house", "haz": "house",
    "csaladi": "house", "ikerhaz": "semi-detached",
    "sorhaz": "terraced", "lakas": "apartment",
    "garzon": "studio", "panel": "apartment",
    "telek": "plot", "nyaralo": "holiday",
    "udulo": "holiday", "iroda": "office",
    "uzlet": "commercial", "muhely": "commercial",
    "garazs": "garage", "mezogazdasagi": "agricultural",
}

SELLER_TYPE_SUFFIXES = ["kft","bt","zrt","nyrt","kkt","bet","ev","egyeni","szovetkezet","alapitvany","iroda","klaszter"]

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
            href = loc.text.strip()
            if href.startswith("https://otthonterkep.hu/ingatlan/"):
                urls.append(href)
        print(f"[otto]  {len(urls)} URLs so far")
        if len(urls) >= max_urls:
            break
    return urls[:max_urls]


def parse_page_data(html):
    for m in re.finditer(r'<script[^>]*>(.*?)</script>', html, re.DOTALL):
        s = m.group(1).strip()
        if not s: continue
        try:
            d = json.loads(s)
            if isinstance(d, dict) and 'uid' in d and 'url' in d:
                return d
        except: pass
    return {}

def parse_jsonld_product(html):
    m = re.search(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m: return {}
    try: d = json.loads(m.group(1))
    except json.JSONDecodeError: return {}
    product = None
    for item in d.get("@graph", []):
        if item.get("@type") == "Product": product = item; break
    if not product: product = d if d.get("offers") else None
    if not product: return {}
    return {"name": product.get("name") or "", "description": product.get("description"), "price": clean_int(product.get("offers", {}).get("price")), "image": product.get("image")}

def parse_summary_boxes_html(html):
    details = {}
    boxes = re.findall(r'<h5[^>]*class="fw-bolder[^"]*"[^>]*>\s*(.*?)\s*</h5>\s*<small[^>]*class="[^"]*summary-data-box[^"]*"[^>]*>\s*(.*?)\s*</small>', html, re.DOTALL)
    for vh, lb in boxes:
        vc = re.sub(r'<[^>]+>', '', vh).strip()
        vc = re.sub(r'\s+', ' ', vc).strip()  # normalize whitespace
        vc = re.sub(r'\s*m2?\s*$', '', vc, flags=re.IGNORECASE).strip()  # strip m2 suffix
        lc = re.sub(r'<[^>]+>', '', lb).strip()
        if lc and vc: details[lc] = vc
    return details

def parse_property_summary_html(html):
    items = {}
    for lbl, val in re.findall(r'<span[^>]*class="property-summary__label"[^>]*>\s*(.*?)\s*</span>\s*<span[^>]*class="property-summary__data[^"]*"[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL):
        lc = re.sub(r'<[^>]+>', '', lbl).strip()
        vc = re.sub(r'<[^>]+>', '', val).strip()
        vc = re.sub(r'\s+', ' ', vc).strip()
        if lc and vc: items[lc] = vc
    return items

def parse_energy_rating_html(html):
    for ct in re.findall(r'<div[^>]*class="energycert[^"]*"(?:[^>]*)>\s*<span[^>]*>\s*(.*?)\s*</span>', html, re.DOTALL):
        ct = re.sub(r'<[^>]+>', '', ct).strip()
        ct = re.sub(r'\s+', ' ', ct).strip()
        if ct: return ct
    return None

def extract_images_html(html):
    urls, seen = [], set()
    for m in re.finditer(r'(https?://images\d*\.ingatlantajolo\.hu/[^"\']*)', html):
        src = m.group(1)
        if "/ad_" in src and "/noimage" not in src and src not in seen:
            seen.add(src); urls.append(src)
    return urls if urls else None

def get_title_from_html(html):
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL)
    if m: return m.group(1).strip()
    return None

def extract_gps_from_city(city, address=""):
    if not city: return None, None
    query = ", ".join(p for p in [address, city, "Magyarorszag"] if p)
    for attempt in range(2):
        try:
            resp = requests.get("https://nominatim.openstreetmap.org/search", params={"format": "json", "q": query if attempt == 0 else city, "limit": 1, "countrycodes": "hu"}, headers={"User-Agent": "OTTHONTERKEP-Scraper/1.0"}, timeout=10)
            data = resp.json()
            if data:
                lat = clean_float(data[0].get("lat"))
                lng = clean_float(data[0].get("lon"))
                if lat and lng: return lat, lng
        except: pass
    return None, None

def scrape_listing(url, browser=None):
    try:
        resp = session.get(url, timeout=30)
        resp.encoding = "utf-8"
        html = resp.text
    except requests.RequestException as e:
        print(f"  x HTTP error: {e}")
        return None

    page_data = parse_page_data(html)
    product = parse_jsonld_product(html)
    details = parse_summary_boxes_html(html)
    property_summary = parse_property_summary_html(html)
    energy = parse_energy_rating_html(html)

    price = product.get("price") or clean_int(page_data.get("price"))
    if not price:
        pm = re.search(r'(\d[\d\s]*\d)\s*Ft', html)
        if pm: price = clean_int(re.sub(r'\s', '', pm.group(1)))

    title = (product.get("name") or "").strip() or page_data.get("url","").split("/")[-1]
    th = get_title_from_html(html)
    if th:
        clean_th = re.sub(r'^Elad[^a-zA-Z]* vagy kiad[^a-zA-Z]* ingatlan itt:\s*', '', th, flags=re.IGNORECASE)
        title = clean_th.strip()
    title = clean_text(title)

    city = clean_text(page_data.get("city"))
    region = clean_text(page_data.get("region"))
    location_raw = ", ".join(p for p in [city, region] if p) if (city or region) else None

    property_type = None
    cat_raw = str(page_data.get("category",""))
    if cat_raw:
        cl = cat_raw.lower().replace(" ","").replace("-","")
        for k,v in PROPERTY_TYPE_MAP.items():
            if k.replace(" ","").replace("-","") in cl: property_type=v; break

    agreement = str(page_data.get("agreement","")).lower()
    listing_type = "sell" if "elado" in agreement else "rent" if "kiado" in agreement else None

    condition_raw = page_data.get("condition")
    if condition_raw and condition_raw not in ("","Atlagos","atlagos","N/A"):
        condition = clean_text(condition_raw)
    else: condition = None

    area = None
    for kl in ("ALAPTERÜLET","ALAPTERULET","TERÜLET","TERULET"):
        v = details.get(kl)
        if v:
            m = re.search(r'(\d+[\d,.]*)', v.replace(",","."))
            if m:
                val = clean_float(m.group(1))
                if val and val > 0: area=val; break

    rooms = None
    v = details.get("SZOBASZÁM") or details.get("SZOBASZAM")
    if v and v.lower() != "nincs megadva":
        m = re.search(r'(\d+(?:[,.]\d+)?)', v.replace(",","."))
        if m:
            val = clean_float(m.group(1))
            if val and val > 0: rooms = str(int(val)) if val==int(val) else str(val)

    year_built = None
    for sk in ("Epites eve","Epites eve:"):
        yb = property_summary.get(sk)
        if yb:
            m = re.search(r'(\d{4})', yb)
            year_built = clean_int(m.group(1)) if m else None; break

    heating = None
    for src in [details.get("FŰTÉS"), details.get("FUTES"), property_summary.get("Fűtés"), property_summary.get("Futes")]:
        if src and src.lower() not in ("nincs megadva","nincs futes"): heating=src; break

    floor = None
    for sk in ("Belső szintek","Belso szintek","Belső szintek:","Belso szintek:"):
        fs = property_summary.get(sk)
        if fs:
            m = re.search(r'(\d+)', fs)
            floor = clean_int(m.group(1)) if m else None; break

    desc = clean_text(product.get("description"))

    seller_name = seller_type = None
    sm = re.search(r'<h2[^>]*class="text-dark[^"]*"[^>]*>\s*(.*?)\s*</h2>', html)
    if sm: seller_name = clean_text(sm.group(1))
    if not seller_name:
        sm2 = re.search(r'<h2[^>]*>(.*?)</h2>', html)
        if sm2: seller_name = clean_text(sm2.group(1))
    if seller_name:
        sl = seller_name.lower()
        for s in SELLER_TYPE_SUFFIXES:
            if s in sl: seller_type=s.upper(); break

    image_urls = extract_images_html(html)

    lat = lng = None
    up = url.split("/")[-1].replace("+"," ").replace("-"," ")
    upc = re.sub(r'\s*\d+\s*$', '', up).strip()
    address_raw = upc.split("/")[-1] if upc else ""
    if city: lat,lng = extract_gps_from_city(city, address_raw)

    plot_sqm = None
    v = details.get("TERULET")
    if v and v.lower()!="nincs megadva":
        m = re.search(r'(\d+[\d,.]*)', v.replace(",","."))
        if m:
            val = clean_float(m.group(1))
            if val and val>0: plot_sqm=val

    price_per_sqm = None
    if price and area and area>0: price_per_sqm = round(price/area)

    return {
        "source_url": url, "source": "otthonterkep",
        "title": title or "no title", "city": city,
        "district": None, "location_raw": location_raw, "price": price,
        "price_per_sqm": price_per_sqm, "area_sqm": area,
        "rooms": rooms, "condition": condition, "heating": heating,
        "year_built": year_built, "floor": floor,
        "property_type": property_type, "listing_type": listing_type,
        "total_floors": None, "balcony_sqm": None,
        "seller_name": seller_name, "seller_type": seller_type,
        "description": desc, "lat": lat, "lng": lng,
        "image_urls": image_urls, "plot_sqm": plot_sqm,
        "energy_rating": energy, "currency": "HUF",
        "listed_at": None,
        "raw_data": json.dumps({
            "price": price, "area": area, "rooms": rooms,
            "lat": lat, "lng": lng, "city": city,
            "condition": condition, "heating": heating,
            "property_type": property_type,
        }, ensure_ascii=False),
        "checksum": compute_checksum({
            "price": price, "area_sqm": area, "rooms": rooms,
            "city": city, "condition": condition, "heating": heating,
        }),
        "is_active": True,
    }

def main(max_listings=50):
    print(f"{'='*60}")
    print("OTTHONTERKEP v4 (HTTP-only, ~0.5s/listing)")
    print(f"{'='*60}\n")
    print("[otto] Fetching sitemap URLs...")
    listing_urls = get_listing_urls(max_listings)
    print(f"[otto] Got {len(listing_urls)} listing URLs\n")
    conn = get_conn()
    scraped = inserted = 0; t_start = time.time()
    for i, url in enumerate(listing_urls, 1):
        t0 = time.time()
        print(f"[{i}/{max_listings}] ...{url[-40:]}")
        result = scrape_listing(url)
        if not result: print("  x failed\n"); continue
        scraped += 1
        if upsert_listing(conn, result):
            inserted += 1
        et = time.time()-t0
        ic = len(result.get("image_urls") or [])
        print(f"  + [{result.get('city','?')}] {str(result.get('title','?'))[:40]} | {result.get('price','?')} Ft | {result.get('area_sqm','?')} m2 | {result.get('rooms','?')} sz | {str(result.get('condition','') or '')[:8]} | {ic}img | {et:.1f}s")
        polite_delay()
    conn.commit()
    et = time.time()-t_start
    print(f"\n{'='*60}\nDONE: {scraped} scraped, {inserted} inserted/updated\nTime: {et:.0f}s ({et/max(scraped,1):.1f}s avg)\n{'='*60}")
    conn.close()

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv)>1 else 50
    main(n)
