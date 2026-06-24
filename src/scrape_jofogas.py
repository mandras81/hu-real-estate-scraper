"""
jofogas.hu/ingatlan scraper v4 — SSR JSON-LD (no Next.js, no Playwright)

2026-06-24: Site refactored to pure SSR. JSON-LD Product contains all fields.
All data extractable from raw HTML — no JS rendering needed.

New in v4:
  image_urls:    main image + all gallery img URLs
  property_type: JSON-LD category -> EN mapping (18 entries)
  condition:     from JSON-LD additionalProperty "Allapot"
  heating:       from "Futes tipusa"
  balcony_sqm:   from "Erkely, terasz"
  plot_sqm:      from "Kert merete"
  rooms/area:    from JSON-LD additionalProperty
"""

import json, re, sys, time, random
import requests

sys.path.insert(0, "/mnt/playground/workspace/workspace-data-engineering/projects/real-estate-scraper/src")
from db import get_conn, upsert_listing, compute_checksum, clean_int, clean_float, clean_text

SESSION_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
DELAY_MIN, DELAY_MAX = 2, 5
SITEMAP_PAGES = ["https://www.jofogas.hu/sitemap.xml?o=%d" % o for o in range(0, 16001, 2000)]

session = requests.Session()
session.headers.update(SESSION_HEADERS)

PROP_TYPE_MAP = {
    "lakas": "flat", "tegla": "flat", "panel": "flat",
    "haz": "house", "hazresz": "house_part",
    "nyaralo": "holiday", "udulo": "holiday",
    "telek": "plot",
    "garazs": "garage",
    "iroda": "office",
    "uzlet": "commercial",
    "termofold": "agricultural",
    "sorhaz": "house", "ikerhaz": "house",
}

COND_MAP = {
    "ujszeru": "new", "uj": "new",
    "felujitott": "renovated",
    "jo allapotu": "good", "jo": "good",
    "kozepes": "average",
    "felujitando": "poor", "rossz": "poor",
}


def polite_delay():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get_listing_urls(max_urls=100):
    urls = []
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


def parse_jofogas_listing(url, html):
    # 1. JSON-LD Product
    m = re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None

    try:
        raw = m.group(1).strip()
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None

    product = None
    for item in d.get("@graph", []):
        if item.get("@type") == "Product":
            product = item
            break
    if not product:
        product = d

    # 2. Extract fields
    props = {}
    for p in product.get("additionalProperty", []):
        name = p.get("name", "")
        val = p.get("value", "")
        if name and val:
            props[name] = val

    offers = product.get("offers", {})
    price = clean_int(offers.get("price"))
    title = clean_text(product.get("name"))

    category = product.get("category", "")
    property_type = None
    if category:
        cat_lower = category.lower().replace(" ", "")
        for k, v in PROP_TYPE_MAP.items():
            if k in cat_lower:
                property_type = v
                break
        if not property_type:
            property_type = cat_lower[:30]

    # Area
    area = None
    for k in ["Méret", "Meret", "Size"]:
        s = props.get(k, "")
        if s:
            m = re.search(r'(\d+[\d,.]*)', s.replace("&sup2;", " ").replace("\xa0", " "))
            area = clean_float(m.group(1).replace(",", ".")) if m else None
            break

    # Rooms
    rooms = None
    for k in ["Szobák száma", "Szobak szama", "Szobák"]:
        rs = props.get(k, "")
        if rs:
            m = re.search(r'(\d+(?:[.,]\d+)?)', rs.replace("+", ""))
            if m:
                rv = clean_float(m.group(1).replace(",", "."))
                rooms = str(int(rv)) if rv and rv == int(rv) else str(rv) if rv else None
            break

    # Condition
    condition = None
    for k in ["Állapot", "Allapot"]:
        cr = props.get(k, "")
        if cr:
            ck = cr.lower().replace(" ", "").strip()
            condition = COND_MAP.get(ck, cr[:30])
            break

    # Heating
    heating = None
    for k in ["Fűtés típusa", "Futes tipusa", "Fűtés"]:
        hv = props.get(k, "")
        if hv:
            heating = clean_text(hv)[:50]
            break

    # Floor count
    floor = None
    for k in ["Szintek száma", "Szintek szama", "Emelet"]:
        fv = props.get(k, "")
        if fv:
            m = re.search(r'(\d+)', fv)
            floor = clean_int(m.group(1)) if m else None
            break

    # Plot size
    plot_sqm = None
    for k in ["Kert mérete", "Kert merete", "Telek méret"]:
        pv = props.get(k, "")
        if pv:
            m = re.search(r'(\d+[\d,.]*)', pv.replace("\xa0", " "))
            plot_sqm = clean_float(m.group(1).replace(",", ".")) if m else None
            break

    # Balcony
    balcony_sqm = None
    for k in ["Erkély, terasz", "Erkely, terasz"]:
        bv = props.get(k, "")
        if bv:
            if bv.lower() not in ("nincs", "nem", ""):
                m = re.search(r'(\d+)', bv)
                balcony_sqm = clean_int(m.group(1)) if m else 1
            break

    # 3. GPS
    lat = lng = None
    mlat = re.search(r'<meta[^>]*(?:property|name)\s*=\s*["\']?place:location:latitude["\']?\s+content=["\']([^"\']+)["\']', html)
    mlng = re.search(r'<meta[^>]*(?:property|name)\s*=\s*["\']?place:location:longitude["\']?\s+content=["\']([^"\']+)["\']', html)
    if mlat and mlng:
        lat = clean_float(mlat.group(1))
        lng = clean_float(mlng.group(1))
    if not lat:
        geo = product.get("geo", offers.get("geo", {}))
        if geo:
            lat = clean_float(geo.get("latitude"))
            lng = clean_float(geo.get("longitude"))

    # Fallback: __NEXT_DATA__ product GPS (has exact coordinates)
    if not lat:
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd_m:
            try:
                nd = json.loads(nd_m.group(1))
                nd_product = nd.get("props", {}).get("pageProps", {}).get("product", {})
                if nd_product.get("latitude") and nd_product.get("longitude"):
                    lat = clean_float(nd_product["latitude"])
                    lng = clean_float(nd_product["longitude"])
            except (json.JSONDecodeError, AttributeError):
                pass

    desc = clean_text(product.get("description"))

    # 4. Seller
    seller_type = "private"
    seller = offers.get("seller", {})
    seller_name = None
    if isinstance(seller, dict) and seller.get("name"):
        seller_name = clean_text(str(seller["name"]))[:80]
        upper = seller_name.upper()
        for suf in ["KFT", "Kft", "BT", "Bt", "ZRT", "Zrt", "INGATLAN"]:
            if suf in upper:
                seller_type = "agent"
                break

    # 5. Image URLs — prefer __NEXT_DATA__ gallery, fallback to JSON-LD
    image_urls = []
    nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd_m:
        try:
            nd = json.loads(nd_m.group(1))
            nd_product = nd.get("props", {}).get("pageProps", {}).get("product", {})
            for img in nd_product.get("images", []):
                u = img.get("url")
                if u and u.startswith("http"):
                    # Prefer bigthumbs for full-res
                    big = u.replace("/thumbs/", "/bigthumbs/")
                    if big not in image_urls:
                        image_urls.append(big)
        except (json.JSONDecodeError, AttributeError):
            pass
    if not image_urls:
        main_img = product.get("image")
        if main_img:
            image_urls.append(main_img)
        for img_match in re.finditer(r'<img[^>]+src="(https?://img\.jofogas\.hu/images/[^"]+)"', html):
            src = img_match.group(1)
            if src not in image_urls:
                image_urls.append(src)
    image_urls = image_urls if image_urls else None

    # 6. City — prefer __NEXT_DATA__ parameters (has 'city' key)
    city = None
    nd_m2 = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nd_m2:
        try:
            nd2 = json.loads(nd_m2.group(1))
            nd_product2 = nd2.get("props", {}).get("pageProps", {}).get("product", {})
            for p in nd_product2.get("parameters", []):
                if p.get("key") == "city":
                    vals = p.get("values", [])
                    if vals:
                        city = clean_text(vals[0].get("value", "").strip())
                        break
        except (json.JSONDecodeError, AttributeError):
            pass
    if not city:
        for k in ["Város", "Varos", "Település", "Telepules", "Helység"]:
            cv = props.get(k, "")
            if cv:
                city = clean_text(cv)
                break

    location_raw = city
    url_path = url.split("/")[-1].replace(".htm", "")
    if not city:
        city = None

    # Year built from JSON-LD additionalProperty or __NEXT_DATA__
    year_built = None
    # JSON-LD: "Építés éve" etc
    for p in product.get("additionalProperty", []):
        pname = p.get("name", "")
        if any(x in pname.lower() for x in ["év", "ev", "year", "built", "építés", "epites"]):
            pval = str(p.get("value", "")).strip()
            ym = re.search(r'(\d{4})', pval)
            if ym:
                year_built = clean_int(ym.group(1))
                break
    if not year_built:
        # Fallback: check __NEXT_DATA__
        nd_m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if nd_m:
            try:
                nd = json.loads(nd_m.group(1))
                nd_product = nd.get("props", {}).get("pageProps", {}).get("product", {})
                for p in nd_product.get("parameters", []):
                    key = p.get("key", "")
                    if key in ("building_date", "year_built", "built_year"):
                        vals = p.get("values", [])
                        if vals:
                            val = vals[0].get("value", "").strip()
                            m = re.search(r'(\d{4})', val)
                            if m:
                                year_built = clean_int(m.group(1))
                                break
            except (json.JSONDecodeError, AttributeError):
                pass

    # 7. Listed at
    listed_at = None
    dt_m = re.search(r'<meta[^>]*(?:property|name)\s*=\s*["\']?article:published_time["\']?\s+content=["\']([^"\']+)["\']', html)
    if dt_m:
        from datetime import datetime, timezone
        try:
            listed_at = datetime.fromisoformat(dt_m.group(1).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            pass

    # Checksum
    record_data = {"price": price, "area_sqm": area, "lat": lat, "lng": lng,
                   "rooms": rooms, "city": city}
    checksum_val = compute_checksum(record_data)

    return {
        "source": "jofogas",
        "source_url": url,
        "title": title,
        "price": price or 0,
        "price_per_sqm": clean_int(price / area) if price and area and area > 0 else None,
        "currency": "HUF",
        "property_type": property_type,
        "listing_type": "sell",
        "location_raw": location_raw,
        "city": city,
        "district": None,
        "lat": lat,
        "lng": lng,
        "area_sqm": area,
        "plot_sqm": plot_sqm,
        "rooms": rooms,
        "floor": floor,
        "total_floors": None,
        "condition": condition,
        "heating": heating,
        "year_built": year_built,
        "balcony_sqm": balcony_sqm,
        "description": desc[:2000] if desc else None,
        "image_urls": image_urls,
        "seller_type": seller_type,
        "seller_name": seller_name,
        "listed_at": listed_at,
        "checksum": checksum_val,
        "raw_data": json.dumps({
            "price": price, "area": area, "rooms": rooms,
            "lat": lat, "lng": lng, "city": city,
            "condition": condition, "heating": heating,
            "category": category,
        }, ensure_ascii=False),
    }


def main(max_listings=50):
    print("=" * 60)
    print("JOFOGAS v4 SSR (JSON-LD, no browser)")
    print("Max: %d listings, delay: %d-%ds" % (max_listings, DELAY_MIN, DELAY_MAX))
    print("=" * 60)

    conn = get_conn()
    listing_urls = get_listing_urls(max_urls=max_listings)
    if not listing_urls:
        print("[jofogas] No URLs from sitemap.")
        return

    inserted = skipped = errors = 0
    for i, url in enumerate(listing_urls, 1):
        print("[%d/%d] ...%s" % (i, len(listing_urls), url[-50:]))
        t0 = time.time()
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print("  x HTTP: %s" % e)
            errors += 1
            polite_delay()
            continue

        record = parse_jofogas_listing(url, resp.text)
        elapsed = time.time() - t0
        if record:
            ok = upsert_listing(conn, record)
            if ok:
                inserted += 1
                pt = record.get("property_type", "?")
                t = (record.get("title") or "")[:30] or "(no title)"
                p = record.get("price", 0)
                a = record.get("area_sqm")
                r = record.get("rooms")
                imgs = len(record.get("image_urls") or [])
                cond = (record.get("condition") or "")[:10]
                print("  + [%-10s] %-30s | %s Ft" % (pt, t[:30], "{:,}".format(p)))
                print("    area=%s m2 rooms=%s cond=%s imgs=%d %.1fs" % (a or "?", r or "?", cond, imgs, elapsed))
            else:
                skipped += 1
                print("  - Exists | %.1fs" % elapsed)
        else:
            errors += 1
            print("  x Parse failed | %.1fs" % elapsed)

        if i < len(listing_urls):
            polite_delay()

    conn.close()
    print("\n" + "=" * 60)
    print("JOFOGAS v4 SUMMARY  Inserted: %d  Updated: %d  Errors: %d" % (inserted, skipped, errors))
    print("=" * 60)


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(max_listings=limit)
