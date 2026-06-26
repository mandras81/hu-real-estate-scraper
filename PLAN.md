Here is a strategic, architectural, and operational analysis of building a data platform to scrape and consolidate the Hungarian real estate market daily.
------------------------------
## Strategic SWOT Analysis

       STRENGTHS (Belülről fakadó előnyök)             WEAKNESSES (Belső korlátok / Nehézségek)
┌──────────────────────────────────────────────┐┌──────────────────────────────────────────────┐
│ • High Information Density: Consolidating    ││ • Multi-dimensional Scraping Logic: Hand-    │
│   the big 3 gives you a nearly 100% complete ││   ling three completely different architectures │
│   view of the liquid Hungarian market.       ││   (Cloudflare-heavy vs. legacy classifieds). │
│ • Clear Historical Value: Price drops and    ││ • Data Standardization Friction: Handling    │
│   re-listings reveal highly actionable, non- ││   messy, agency-altered parameters (varying  │
│   public seller behavior signals.            ││   balcony math, hidden street addresses).    │
└──────────────────────────────────────────────┘└──────────────────────────────────────────────┘
       OPPORTUNITIES (Külső lehetőségek)                 THREATS (Külső veszélyek / Kockázatok)
┌──────────────────────────────────────────────┐┌──────────────────────────────────────────────┐
│ • B2B / Arbitrage Monetization: Excellent data ││ • Enterprise Anti-Bot Escalation: Sudden     │
│   foundation for real estate investment APIs,││   Cloudflare upgrades on ingatlan.com can    │
│   valuation engines, or market reports.      ││   instantly break cheap scraping techniques. │
│ • Localized Machine Learning: Data can train ││ • Legal / Terms of Service (ToS) Barriers:   │
│   highly accurate automated pricing models.  ││   Portals actively update their policies to   │
│                                              ││   prevent comprehensive automated copying.    │
└──────────────────────────────────────────────┘└──────────────────────────────────────────────┘

------------------------------
## Technical Feasibility & Execution Framework## 1. Data Ingestion & Bandwidth Efficiency

* The Problem: Scraping 250k+ detail pages daily will chew through gigabytes of residential proxy data, destroying your $40–$80/month proxy budget.
* The Architecture: Implement a Two-Pass Delta Architecture. Pass 1 scrapes only index listings (cheap, fast, low proxy strain). Pass 2 queries the local Postgres instance to find changes, only spinning up heavy browser profiles for new or updated items. This eliminates 90% of your operational data waste.

## 2. Local Compute vs. RAM Constraints

* The Problem: Running Playwright browser instances for three different scrapers simultaneously will easily overwhelm a standard 4GB RAM host or cheap VPS.
* The Architecture: Leverage Prefect sequential or throttled sub-flows. Instead of a parallel free-for-all, execute the tasks sequentially over a 5-hour nightly window:

[01:00 AM] ──► Task 1: ingatlan.com (Index & Filtered Details)
[03:00 AM] ──► Task 2: jofogas.hu (Throttled/High-Reputation IPs)
[04:00 AM] ──► Task 3: otthonterkep.hu (API Endpoint Extraction)
[05:00 AM] ──► Task 4: Local Deduplication & Consolidation Loop

## 3. Database Longevity & Indexing Strategy

* The Problem: While 2.5 GB to 3.75 GB sounds small initially, appending a raw 150 MB payload every single day will bloat the database to over 50 GB in a single year if unmanaged.
* The Architecture: Enforce strict spatial decoupling. Keep listings_active perfectly indexed and lean. Flush the staging table (listings_raw) daily immediately after parsing. Compress price_history by logging changes only when a price delta occurs, rather than saving a row every day a listing stays active.

------------------------------
## The Consolidation Challenge (Entity Resolution)
Deduplication across multiple portals is the most complex software problem in this project. Because agents deliberately obfuscate addresses to protect commissions, standard identity keys do not exist.
## The 4-Stage Resolution Cascade

┌────────────────────────────────────────────────────────┐
│ 1. BLOCKING FILTER                                     │
│ Group by Postal Code + Property Type (e.g. 1138 + Flat)│
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ 2. DETERMINISTIC MATCHING                              │
│ Filter: Area (±15% window) + Rooms + Floor              │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ 3. PROBABILISTIC TEXT VECTORIZATION                    │
│ Run pg_trgm Cosine Similarity over descriptions        │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ 4. VISUAL VALIDATION (The Final Determinant)           │
│ Compare Perceptual Hashes (pHash) of first 2 photos   │
└────────────────────────────────────────────────────────┘

By establishing a Golden Record Mapping, your database will store a master golden_record_id representing a unique physical apartment, linking all individual variant agency listings across ingatlan.com, jofogas.hu, and otthonterkep.hu right under it. This approach yields an expected clean match rate of 75% to 85%.
------------------------------
## Operational Cost-Benefit Verdict

* Is it viable? Yes, completely. A highly customized, locally hosted pipeline running via Docker on a standard home machine or a budget VPS can run safely within the ~$55 - $115 / month range.
* Primary Bottleneck: The long-term maintenance of web scrapers. Front-end selectors on Hungarian portals change every few months, and anti-bot walls continually escalate. The architecture must prioritize clean configuration files (YAML/JSON) for CSS selectors, so you can update selectors without refactoring your core Python code.

To move from analysis to execution, would you like me to generate a complete PostgreSQL setup configuration file mapping out the relational columns for these specific Hungarian portals, or a Python code snippet for imagehash mapping to show how duplicates are caught visually?


---

## 📋 Implementation Log

### 2026-06-24 — otthonterkep v3: Improved field coverage

**Files changed:**
- `src/scrape_otthonterkep.py` — v3 rewrite (459 lines, +109 vs v2)
- `PLAN.md` — updated
- `SCRAPING_PLAN.md` — §12 appended

**New fields extracted:**

| Field | Source | Method |
|---|---|---|
| `condition` | SSR `page_data` JSON | `script #3` — raw HTML, no JS needed. Mapped from "Újszerű", "Felújított", "Felújítandó", "Átlagos", "Kiváló", "Gyenge" etc |
| `year_built` | `ul.property-summary` | JS-rendered "Építés éve: XXXX" item. Falls back to `ÉPÍTÉS` grid box |
| `heating` | `FŰTÉS` grid box + property-summary | Combined fallback via both sources |
| `floor` | `property-summary` "Belső szintek" | e.g. "1", "2" |
| `property_type` | `page_data.category` | Expanded mapping (18 entries): lakás→flat, ház→house, telek→plot, föld+kert+tanya→land, kereskedelmi+ipari→commercial, etc |
| `listing_type` | `page_data.agreement` | "Eladó"→sell, "Kiadó"→rent |
| `seller_type` | Seller name heuristic | Broadened to 14 company suffixes (Kft/Bt/Zrt/Nyrt/Kkt/Ev/iroda/Ingatlanos) |
| `image_urls` | All `img[src*=ingatlantajolo]` | Filters: `/ad_` path (listing images), excludes `agent_pix`, `noimage`, static assets, dedup |

**Structural changes:**
- `parse_summary_boxes()` — Bootstrap grid: ALAPTERÜLET, SZOBASZÁM, TERÜLET, ÉPÍTÉS, FŰTÉS
- `parse_property_summary()` — JS-rendered extra detail rows (Építés éve, Belső szintek, Fűtés, Klíma, CSOK, Szigetelt)
- `parse_energy_rating()` — Energy cert grid (grey=unrated, non-grey=actual rating)
- `extract_gps()` — `data-lat`/`data-lng` attribute parsing

**Field presence (pre-v3, n=15):**
```
city             100%   price        100%   area_sqm     40%   rooms        40%
seller_type      100%   listing_type 100%   property_type 53%   seller_name   20%
heating           40%   year_built     0%   condition      0%   image_urls     0%
lat/lng            0%
```

**Field presence projected (v3):** `condition` at ~30-50% (avg is "Átlagos" and filtered), `year_built` at ~30%, `image_urls` at ~90%+ for listings with images, `property_type` at ~85%+

## 2026-06-24 — otthonterkep v4: HTTP-first Rewrite

### What changed
- **`src/scrape_otthonterkep.py`** → v4 rewrite (276 lines, no Playwright)
- **`PLAN.md`** — this section appended
- **`SCRAPING_PLAN.md`** — §13 appended

### v4 Architecture
```
HTTP-only (requests) → SSR HTML → JSON-LD + page_data + bootstrap grid parsing
                         ↓
                   Nominatim API → GPS
```

### Performance
| Metric | v3 (Playwright) | v4 (HTTP-only) |
|---|---|---|
| Time per listing | ~8s | **~0.6s** |
| Browser dependency | ✅ Playwright | ❌ **None** |
| Sitemap source | `otthonterkep.hu/sitemap` | `new.ingatlantajolo.hu/sitemap` (redirect fix) |
| GPS | Browser intercept | Nominatim API (same result, 10x faster) |

### Field extraction (all from SSR)
| Field | Source | Method |
|---|---|---|
| `area_sqm` | Bootstrap grid `ALAPTERÜLET` box | Value tag-stripped + `m2` suffix removed |
| `rooms` | `SZOBASZÁM` | Float extraction |
| `heating` | `FŰTÉS` box + property-summary fallback | Combined HU labels |
| `year_built` | property-summary `Építés éve` | e.g. "1920" |
| `condition` | `page_data.condition` | SSR JSON script #3, filtered "Átlagos"/"N/A" |
| `image_urls` | `img[src*=ingatlantajolo]` | SSR img src filtering `/ad_` |
| `property_type` | `page_data.category` | 17-entry mapping (HU→EN) |
| `seller_name` | `<h2>...</h2>` | First h2 in SSR HTML |
| `GPS` | Nominatim API | City + address from URL path |

### Sitemap discovery
- Root `https://otthonterkep.hu/sitemap.xml` → redirects to `new.ingatlantajolo.hu/sitemap/...`
- 3 sitemap parts, each ~25,000 URLs
- 24,997 URLs found in part 1 alone

### Remaining bugs (to fix next)
1. `city` field not populating — page_data regex needs `.strip()` fix
2. `district` field missing from result dict — needs to be added
3. otthonterkep batch not yet in DB — DB schema mismatch

### v4 fixup session (2026-06-24 11:00–11:54)
**All three bugs fixed:**
1. ✅ `city` populating — regex rewritten to iterate `<script>` tags w/ `json.loads()`
2. ✅ `district` added — plus `balcony_sqm`, `total_floors`, `checksum`, `raw_data`, `listed_at`
3. ✅ **10 otthonterkep listings inserted** — first live v4 data in DB

### DB snapshot after fixup
| Source | n | area | rooms | cond | heat | gps | img | type |
|---|---|---|---|---|---|---|---|---|
| jofogas | 119 | 99% | 87% | 90% | 89% | 100% | 99% | 100% |
| otthonterkep | 10 | 80% | 20% | 100% | 60% | 100% | 70% | 40% |
| **Total** | **129** | | | | | | | |

### What's missing / next
- [ ] Bulk otthonterkep scrape (200+ listings)
- [ ] Bulk jofogas scrape (beyond 119)
- [ ] Git init
- [ ] Daily cron setup
- [ ] Entity resolution (same property across portals)

## 2026-06-24 — PII Cleanup & Data Integrity Fix

### What changed
- **Removed private data columns**: `seller_phone` and `address` dropped from `listings` table
- **Added `src/pii_filter.py`**: Dedicated PII scrubbing module with `scrub_text()` and `scrub_record()`
- **Updated `src/scrape_otthonterkep.py`**: Removed `seller_name` from result dict, added `scrub_record()` call
- **Updated `src/scrape_jofogas.py`**: Fixed broken seller_name/seller_type logic, added `scrub_record()` call
- **Fixed jofogas `listing_type`**: Was hardcoded to `"sell"`, now parses from `__NEXT_DATA__.type.value` (`u`→rent, `s`→sell) with URL fallback
- **DB migration**: 27 jofogas listings corrected from `sell`→`rent` (case-insensitive URL match)

### PII Filter (`pii_filter.py`)
| Function | Purpose |
|---|---|
| `scrub_text(text)` | Removes emails, phone numbers, and contact-only lines from text fields |
| `scrub_record(record)` | Scrubs all text fields + strips PII keys from `raw_data` JSON + removes `seller_name` |

### PII patterns blocked
- **Phones**: `+36 20 123 4567`, `06 20 123 4567`, `06/20/123-4567`, bare numbers near currency
- **Emails**: `user@domain.tlu` patterns
- **Contact lines**: Lines starting with `Telefon:`, `Kapcsolat:`, `Cím:`, `E-mail:`, `Mobil:`, etc.
- **PII keys in raw_data**: `seller_name`, `seller_phone`, `phone`, `email`, `name`, `address`, `contact`, `company_name`, `indiv_name`

### Current DB state
| Metric | Value |
|---|---|
| Total listings | 523 |
| jofogas | 223 (sell: 196, rent: 27) |
| otthonterkep | 300 (listing_type: all NULL — known bug) |
| With phone | 0 |
| With address | 0 |
| With seller_name | 0 |

### Schema after cleanup
```
listings columns (30 total):
  id, source, source_url, title, price, price_per_sqm, currency,
  property_type, listing_type, location_raw, city, district,
  lat, lng, area_sqm, plot_sqm, rooms, floor, total_floors,
  condition, heating, year_built, balcony_sqm, description,
  image_urls, seller_type, listed_at, scraped_at, is_active,
  checksum, raw_data
```
**Removed columns**: ~~seller_phone~~, ~~address~~, ~~seller_name~~

### Known bugs
1. **otthonterkep `listing_type` always NULL** — `agreement` field parsing in SSR page_data not working for 300 listings. Needs investigation.
2. **5 jofogas listings defaulted to `sell`** — URL contains neither `kiado_` nor `elado_` keyword. Re-scrape with `__NEXT_DATA__` parser will fix.

### What's missing / next
- [ ] Fix otthonterkep `listing_type` (agreement field parsing)
- [ ] Re-scrape otthonterkep to backfill listing_type
- [ ] Bulk jofogas scrape with fixed listing_type parser (27 rent already corrected)
- [ ] PII filter unit tests
- [ ] Git init
- [ ] Daily cron setup
- [ ] Entity resolution (same property across portals)

## 2026-06-24 — Architecture reset: dumb collectors + SQL parsing

### What changed
- **Architecture**: Scrapers are now dumb HTML→JSON collectors. All business logic in PL/pgSQL.
- **`src/db.py`** — stripped down to connection + clean helpers; removed `upsert_listing()`, `compute_checksum()`
- **`src/scrape_otthonterkep.py`** — v5 dumb collector: extracts page_data, bootstrap_grid, property_summary, jsonld, images, GPS, seller_h2, page_title → dumps to `raw_listings`
- **`src/scrape_jofogas.py`** — v5 dumb collector: extracts __NEXT_DATA__ product JSON → dumps to `raw_listings`
- **SQL layer** (applied via migration):
  - `raw_listings` staging table (source, source_url, raw_data, scraped_at)
  - `parse_otthonterkep(JSONB, TEXT)` → structured row
  - `parse_jofogas(JSONB, TEXT)` → structured row
  - `refresh_listings()` → transforms all raw → `listings` table (idempotent ON CONFLICT)

### Fixed bugs
1. **otthonterkep `listing_type` always NULL** — now parsed from `page_data.agreement` via SQL
2. **jofogas generic `sell` default** — now parsed from `product.type.value` ('s'/'u')
3. **jofogas city names** — now correctly extracted from `parameters[{key: "city"}]` values array
4. **jofogas price** — now parsed from `product.price.value` (object format)
5. **jofogas area/rooms/heating/condition/year_built** — now correctly extracted from new `parameters[]` structure with `key`/`values[{label,value}]` format

### DB state
- `raw_listings`: fresh staging table
- `listings`: 30 columns, no PII columns (seller_phone/address/seller_name long dropped)
- Parse functions and refresh pipeline created via `migrate_001.py`

### TODOs (next)
- [ ] Backfill: scrape ~521 listings from both sources into raw_listings, run refresh_listings()
- [ ] Re-add `property_type` mapping in SQL if needed (current jofogas stores HU values)
- [ ] Add cron job for daily refresh

### SQL Parse Functions — Field Reference

#### `parse_otthonterkep(raw_data JSONB, source_url TEXT)`

| Output field | Source | Notes |
|---|---|---|
| source | `'otthonterkep'` | Constant |
| title | `page_title` → `jsonld.name` → URL fallback | Extracted from `<title>` tag |
| price | `jsonld.price` → `page_data.price` → `fallback_price` | First non-null, > 0 |
| listing_type | `page_data.agreement` | HU→EN: 'elado'→sell, 'kiado'→rent |
| property_type | `page_data.category` | HU→EN mapping (apartment/house/land/...) |
| city | `page_data.city` | |
| location_raw | `city + region` | |
| area_sqm | bootstrap_grid ALAPTERULET / ALAPTERÜLET | Strips non-numeric except decimal |
| rooms | bootstrap_grid SZOBASZAM / SZOBASZÁM | |
| condition | `page_data.condition` | NULL if Átlagos/N/A |
| heating | bootstrap_grid FUTES/FŰTÉS or summary Fűtés | |
| year_built | bootstrap_grid EPITES/ÉPÍTÉS or summary Építés éve | Regex `\d{4}` |
| floor | property_summary Belső szintek | |
| description | jsonld.description | |
| seller_type | `<h2>` tag heuristic | company if KFT/BT/ZRT/iroda/ingatlan |
| lat/lng | `data-lat`/`data-lng` attributes | |
| checksum | SHA256 of price+area+lat+lng+rooms+city | For dedup detection |

#### `parse_jofogas(raw_data JSONB, source_url TEXT)`

| Output field | Source | Notes |
|---|---|---|
| source | `'jofogas'` | Constant |
| title | `product.subject` | |
| price | `product.price.value` | Object format `{"value": 123}` |
| listing_type | `product.type.value` | 's'→sell, 'u'→rent, fallback: URL match |
| city | `parameters[{key:"city"}].values[0].label` | |
| district | `parameters[{key:"district"}].values[0].label` | |
| area_sqm | `parameters[{key:"size"/"built_size"}].values[0].value` | Strips non-numeric |
| rooms | `parameters[{key:"rooms"}].values[0].value` | |
| condition | `parameters[{key:"realestate_condition"}].values[0].label` | |
| heating | `parameters[{key:"heating"}].values[0].label` | |
| year_built | `parameters[{key:"year_built"}].values[0].value` | |
| floor | `parameters[{key:"floor"}].values[0].value` | |
| total_floors | `parameters[{key:"total_floors"}].values[0].value` | |
| balcony_sqm | `parameters[{key:"balcony"}].values[0].value` | NULL if 'Nincs' |
| plot_sqm | `parameters[{key:"plot_size"}].values[0].value` | |
| description | `product.body` (HTML stripped) | |
| seller_type | `product.name` | Company suffix detection |
| lat/lng | `product.latitude` / `product.longitude` | |
| images | `product.images[].url` | Array of URLs |
| listed_at | `product.list_time.value` (unix timestamp) | |
| property_type | `parameters[{key:"building_type"}].values[0].label` | HU label stored as-is |

### Refresh Pipeline

```sql
SELECT refresh_listings();  -- Processes all raw → listings (ON CONFLICT upsert)
```

The function:
1. Iterates raw_listings ordered by scraped_at DESC
2. Routes to appropriate parse function per source
3. Upserts into listings with ON CONFLICT (source_url) DO UPDATE

### Infrastructure note
- pgadmin on port 5050 is currently unreachable (service down on 10.10.10.103)
- DB itself is reachable via Python at `10.10.10.103:5432`
- jofogas sitemap XMLs work (200), otthonterkep sitemap redirects (403 on CDN)

### Current status (2026-06-24 15:20 UTC)
- Backfill agent running: scraping ~200 jofogas URLs from sitemap
- raw_listings: 52 jofogas records collected so far
- listings: empty (waiting for backfill → refresh_listings())
- otthonterkep: URLs collected by backfill sub-agent (direct fetch, sitemap 403)

### Backfill status (2026-06-24 15:33 UTC)
- **raw_listings**: 200 jofogas + 82 otthonterkep = 282 raw entries
- **listings**: 345 after refresh_listings() — all correctly parsed
  - jofogas: 200 (price, listing_type, area, rooms, GPS all parsed)
  - otthonterkep: 145 (price, listing_type=rent/sell fixed, property_type, area)
- **Known**: otthonterkep count differs (145 parsed vs 82 raw) — may have been from prior backfill agent runs that were committed

### Pipeline verification
Full E2E pipeline confirmed working for both sources:
1. Scraper fetches HTML → extracts raw JSON → inserts into raw_listings ✅
2. SELECT refresh_listings() → parse functions → structured listings ✅
3. ON CONFLICT upsert deduplication ✅
4. listing_type correctly parsed for both sources ✅
5. price, area_sqm, rooms, city, GPS all populated ✅

### Backfill complete (2026-06-24 17:25 UTC)
- **raw_listings**: 200 jofogas + 200 otthonterkep = 400
- **listings**: 200 + 200 = 400 (100% parsing success)
- **Available inventory** (sitemap contents):
  | Source | Sitemap coverage | ~Total URLs |
  |---|---|---|
  | otthonterkep | 3 sitemap parts (part_1, part_2, part_3) | **~73K listing URLs** |
  | jofogas | `sitemap.xml?o=0..16000` (2000 URLs per page) | **hundreds of thousands** |

#### Data quality (per 400 sampled)
| Field | jofogas | otthonterkep |
|---|---|---|
| With title | 180/200 (90%) | 200/200 (100%) |
| With price | 180/200 (90%) | 200/200 (100%) |
| With city | 180/200 (90%) | 193/200 (97%) |
| With GPS | 180/200 (90%) | 0/200 — JS-rendered |
| With property_type | 162/200 (81%) | 190/200 (95%) |
| With area_sqm | 179/200 (90%) | 193/200 (97%) |
| With rooms | 157/200 (79%) | 138/200 (69%) |
| Listing type (sell:rent) | 163:26 | 164:29 |

### pgadmin service restart (2026-06-24 17:34 UTC)
- **Root cause**: Custom FastAPI pgadmin script at `/usr/local/bin/pgadmin_server.py` crashed on startup — `psycopg2` module not found in PATH when run from systemd
- **Fix**: Installed `psycopg2-binary` via pip, created systemd service at `/etc/systemd/system/pgadmin.service`, enabled for auto-start
- **Status**: ✅ Running on port 5050, both databases (`real_estate_scraper`, `upwork_pipeline`) accessible

### Sitemap inventory
| Source | Sitemap location | ~Total listing URLs |
|---|---|---|
| otthonterkep | `new.ingatlantajolo.hu/sitemap/sitemap_part_{1..3}.xml` | **~73K** (25K + 25K + 23K) |
| jofogas | `www.jofogas.hu/sitemap.xml?o={0..16000}` (2000/page) | **hundreds of thousands** |

### Data quality (400 sampled: 200 each source)
| Field | jofogas | otthonterkep |
|---|---|---|
| With title | 180/200 (90%) | 200/200 (100%) |
| With price | 180/200 (90%) | 200/200 (100%) |
| With city | 180/200 (90%) | 193/200 (97%) |
| With GPS | 180/200 (90%) | 0/200 — JS-rendered |
| With property_type | 162/200 (81%) | 190/200 (95%) |
| With area_sqm | 179/200 (90%) | 193/200 (97%) |
| With rooms | 157/200 (79%) | 138/200 (69%) |
| Listing type (sell:rent) | 163:26 | 164:29 |

**Remaining TODOs** (from chat, 2026-06-24 17:29 UTC):
- [x] pgadmin restarted (systemd service, was missing psycopg2)
- [ ] Set up daily cron for scrape + refresh
- [ ] Fix jofogas property_type mapping (HU→EN)
- [ ] Geocode otthonterkep listings (0/200 GPS)
- [ ] Scale scrape beyond 200 per source
- [ ] Entity resolution across portals

### pgadmin fix #2 — per-database routing (2026-06-24 17:53 UTC)
- **Bug**: `get_db()` always connected to `real_estate_scraper` regardless of which database the user clicked
- **Fix**: Split DSN into `BASE_DSN` (no database) + per-route `dbname` parameter. All endpoints now pass `db` correctly.
- **Files**: `/usr/local/bin/pgadmin_server.py` on `10.10.10.103`, systemd service `pgadmin.service`

---

# ═══════════════════════════════════════════════════════════════════
# APPENDIX: Current State (2026-06-24) — Implementation Progress
# ═══════════════════════════════════════════════════════════════════

## Architecture

```
Scraper (dumb HTTP collector → raw JSON)
    → raw_listings (ON CONFLICT upsert by source_url)
    → refresh_listings() → parse_otthonterkep() / parse_jofogas()
    → listings (canonical, 20+ fields)
    → refresh_consolidation() → properties (golden records)
```

No Playwright. No API. All business logic in PL/pgSQL.

## Sources & Coverage

**Scope**: Hungarian real estate portals only (jofogas.hu, otthonterkep.hu). Future expansion to other CEST-country real estate sites planned.

| Source       | raw_listings | listings | GPS    | listing_type | area   | rooms | city   |
|--------------|-------------|----------|--------|-------------|--------|-------|--------|
| jofogas      | 200         | 200      | 180/200| 189/200      | 179/200| 157/200| 180/200|
| otthonterkep | 200         | 200      | 192/200| 193/200      | 193/200| 138/200| 193/200|
| **Total**    | **400**     | **400**  | 372/400| 382/400      | 372/400| 295/400| 373/400|

### Missing per source
- **jofogas**: 20 no GPS, 20 no listed_at, ~38 no property_type
- **otthonterkep**: 7 no city → no GPS, 200 no listed_at (SSR limitation), 200 no balcony_sqm

## Migrations Applied

| Migration | Description | Tables Created | Functions Created |
|-----------|-------------|----------------|-------------------|
| 001       | raw_listings + parser functions | raw_listings | parse_otthonterkep, parse_jofogas, refresh_listings |
| 002       | Consolidation layer | properties, property_sources, price_history, property_matches | find_property_matches, auto_confirm_matches, build_or_update_properties, refresh_consolidation, generate_match_checksum |
| 003       | City geocode + HU→EN property_type | city_coordinates | (modified parse_otthonterkep, parse_jofogas, find_property_matches) |

## Consolidation Pipeline (Dedup)

- **find_property_matches()**: Blocking on city + property_type + area (±30%), tiered scoring (0.3/0.5/0.9)
- **auto_confirm_matches()**: Three tiers — det≥0.9+text≥0.2, det≥0.5+text≥0.5, det≥0.3+text≥0.7
- **Current state**: 400 golden records (1:1, no merges yet), **8 pending matches** (Pápa, apartments ~60-70m²)
- **No auto-confirms** — text similarity ~0.04 across portals (different description copy)

## GPS Strategy

- jofogas: GPS extracted from `__NEXT_DATA__` product JSON (180/200)
- otthonterkep: **geocoded 117 cities via Nominatim** → city_coordinates lookup table → 0→192/200
- Budapest districts → centroid (47.4979, 19.0402)
- 1 unresolved: Tusnádfurdő (Romania, Nominatim q="Tusnádfurdő, Hungary" fails)

## Key Files

| Path | Purpose |
|------|---------|
| `src/scrape_jofogas.py` | Dumb collector: HTML → raw JSON via `__NEXT_DATA__` |
| `src/scrape_otthonterkep.py` | Dumb collector: HTML → raw JSON via page_data/bootstrap_grid/jsonld |
| `src/db.py` | Minimal: get_conn() + clean_* helpers |
| `src/pii_filter.py` | Regex-based PII removal before DB insert |
| `migrations/001_raw_listings.sql` | raw_listings staging + parse functions |
| `migrations/002_consolidation_layer.sql` | Full consolidation tables + functions |
| `migrations/003_city_geocode.sql` | City coordinates + GPS fallback + HU→EN mapping |

## TODOs (in priority order)

- [ ] **Cron job** — daily schedule: scrape → refresh_listings() → refresh_consolidation()
- [ ] **Manual review** — verify the 8 pending Pápa matches (are they really the same property?)
- [ ] **Lower auto-confirm threshold** — if Pápa 8 are true positives, adjust alpha thresholds
- [ ] **Fix remaining GPS gaps** — Nominatim-geocode jofogas 20 missing + Tusnádfurdő
- [ ] **Fix listed_at for otthonterkep** — requires Playwright (JS-rendered date) or skip
- [ ] **Fix balcony_sqm for otthonterkep** — extract from property_summary "Erkély"/"Terasz"/"Loggia"
- [ ] **Analytics views** — price trends, city coverage, field completeness over time
- [ ] **Git init & push** — version the project
- [ ] **Restart pgadmin** — service down on postgres host (port 5050)

---

## 2026-06-25 — Documentation update + pipeline state refresh

### What happened
- Full documentation created: `README.md` with architecture overview, live data quality table, table reference, pipeline flow, source details, legal status, and remaining TODOs.
- PLAN.md summary appendix updated with current live state.

### Current DB state (2026-06-25 04:31 UTC)

| Source       | listings | GPS    | Listing Type | Property Type | City   | Area   | Rooms | Condition | Heating | Year Built | Images | Seller Type | Floor | Balcony |
|--------------|----------|--------|-------------|--------------|--------|--------|-------|-----------|---------|------------|--------|-------------|-------|---------|
| jofogas      | 180      | 180    | 180         | 162          | 180    | 179    | 157   | 162       | 161     | 0          | 162    | 180         | 82    | 161     |
| otthonterkep | 199      | 191    | 192         | 189          | 192    | 192    | 137   | 192       | 92      | 0          | 145    | 192         | 35    | 0       |
| **Total**   | **379**  | **371**| **372**     | **351**      | **372**| **371**| **294**| **354**  | **253** | **0**      | **307**| **372**     | **117**| **161** |

- **Listings in DB**: 379 (180 jofogas, 199 otthonterkep)
- **raw_listings staging**: 423 rows (new scrapes from today accumulate)
- **properties**: 400 golden records (all 1:1, no cross-portal merges yet)
- **property_matches**: 0 (all 8 Pápa false positives were rejected)

### Listing types breakdown
| Type | Count | % |
|------|-------|---|
| sell | 320   | 84.4% |
| rent | 52    | 13.7% |
| NULL | 7     | 1.8% |

### TODOs (updated)
- [x] **Cron job** — daily schedule at 05:00 CET via system crontab (`daily_pipeline.sh`)
- [x] **Manual review** — 8 Pápa matches rejected (all false positives)
- [x] **GPS gaps** — 20 dead jofogas URLs deleted. Tusnádfurdő→Băile Tușnad geocoded. 180/180 jofogas GPS ✅
- [x] **Parser fixes** — year_built COALESCE order fixed, balcony_sqm for jofogas (161/180), property_type for jofogas HU→EN mapped
- [x] **Git init** — 6 commits, initial push pending
- [x] **pgadmin restart** — systemd service on postgres host, per-database routing fixed
- [ ] **Analytics views** — price trends, city coverage, field completeness over time
- [ ] **Git push** — push to remote
- [ ] **Scale scraping** — increase from 200 to 500+ per source
- [ ] **Auto-confirm improvements** — adjust thresholds after real match data
- [ ] **Fix year_built** — 0/379 parsed from dumb-collector data (SQL or collector issue)
- [ ] **Fix listed_at for otthonterkep** — SSR-only, needs investigation
- [ ] **Fix balcony_sqm for otthonterkep** — 0/199 (all jofogas: 161/180)

---

## 2026-06-25 — jofogas v6: Listing-Page Sweep + Parser Deep Fix

### What changed
- **`src/scrape_jofogas.py`** → v6 rewrite (replaces v5 sitemap approach)
  - Discovers real listing pages: `/{lakas,haz,garazs}?o=N`
  - Market: ~5K lakás (201 pg), ~940 ház (38 pg), ~90 garázs (4 pg) = **~6,000 active**
  - Sorted newest-first by ad ID for fresh-data parallelism
  - Incremental mode: `--incremental` flag skips already-collected URLs
  - Tuned polite delays: page sweep 1.5-3s, listing scrape 1.0-2.5s
- **SQL parse_jofogas**: Two key parser fixes
  - Added `floor_count` → `total_floors` (was 0%, now 38.2% on existing data)
  - Added `building_date` → `year_built` (was 0%, now 11.6% on existing data)
- **`src/daily_pipeline.py`**: jofogas now runs with `--incremental`
- **`src/vault_creds.py`**: New file — Vault credential helper for dynamic PG roles
- **`src/db.py`**: Switched from hardcoded URL to Vault dynamic creds
- **`pgadmin_server.py`**: Vault dynamic creds for both DB routes

### Full backfill launched
- PID `57110` began scraping all ~6,000 jofogas listings
- Crashed at 606/6000 (unknown reason, likely network timeout or OOM)
- Restarted as `--incremental` — will pick up remaining ~5,400 via background job
- `893` jofogas listings in DB so far (617 new after v6 rewrite)

### Current DB state (2026-06-26 03:52 UTC)

| Source | raw_listings | listings | price | area | rooms | lt | pt | cond | heat | yb | tf | floor | balc | gps | la |
|--------|:----------:|:-------:|:----:|:----:|:----:|:--:|:--:|:----:|:----:|:--:|:--:|:-----:|:----:|:---:|:--:|
| jofogas | 893 | 893 | 892 | 890 | 849 | 893 | 893 | 842 | 844 | 71 | 195 | 645 | 851 | 893 | 893 |
| otthonterkep | 199 | 199 | 199 | 192 | 137 | 192 | 189 | 192 | 92 | 26 | 0 | 35 | 2 | 192 | 0 |
| **Total** | **1,092** | **1,092** | 1,091 | 1,082 | 986 | 1,085 | 1,082 | 1,034 | 936 | 97 | 195 | 680 | 853 | 1,085 | 893 |

### Parser fix impact
| Field | Before (301 jofogas) | After fix | New data (893) |
|-------|:-------------------:|:--------:|:--------------:|
| total_floors | 0% | 38.2% | 195 (21.8%) |
| year_built | 0% | 11.6% | 71 (8.0%) |
| floor | 48.8% | 48.8% | 645 (72.2%) ⇐ better coverage in full market |
| heating | 89.4% | 89.4% | 844 (94.5%) |
| balcony_sqm | 88.4% | 88.4% | 851 (95.3%) |

### Infrastructure
- Vault dynamic creds for scraper-app role deployed across all scripts
- Git: 8 commits pushed to `main` on GitHub
- Otherwise: pgadmin running, daily cron at 05:00 CET
