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
