# Real Estate Scraper — Hungarian Property Pipeline 🇭🇺🏠

**Dumb HTTP scrapers → PostgreSQL → PL/pgSQL parsing → entity resolution**.

**Scope**: Hungarian real estate portals (jofogas.hu, otthonterkep.hu).  
**Architecture**: Scrapers are zero-business-logic HTML→JSON collectors. All parsing in PL/pgSQL.

---

## Quick Start

```bash
# Daily pipeline (1000 listings per source, incremental)
./daily_pipeline.sh 1000

# Step by step
python3 src/scrape_jofogas.py --incremental 1000
python3 src/scrape_otthonterkep.py --incremental 1000

# Full backfill
python3 src/scrape_jofogas.py 6000
python3 src/scrape_otthonterkep.py --incremental 5000
```

---

## Architecture

```
HTTP (requests) → SSR HTML → raw JSON → raw_listings (staging table)
    → refresh_listings() → parse_otthonterkep() / parse_jofogas()
    → listings (canonical, 20+ fields)
    → refresh_consolidation() → properties (golden records)
```

**No Playwright. No API. No business logic in Python.**

### Principles
- **Schema-first**: Raw JSON dumped as-is. Parsing contracts defined in SQL.
- **Idempotent**: `refresh_listings()` uses `ON CONFLICT (source_url) DO UPDATE`.
- **Traceable**: Every listing links back to its raw `raw_data` JSON.
- **PII-free**: `pii_filter.py` strips phones/emails/contact lines before insert.

---

## Current State (2026-06-26 09:16 UTC)

| Source | Active Market | Collected | Strategy | Progress |
|--------|:------------:|:--------:|----------|:-------:|
| **jofogas** | ~6,000 | **1,784** | Listing page sweep `/{cat}?o=N` + incremental | ✔ Complete |
| **otthonterkep** | ~73,000 | **1,615** (±200/h) | Sitemap crawl 5K/day @ `--incremental` | ▶ 1.8K/5K backfill |
| **Total** | **~79,000** | **3,399** | Polite daily pipeline | **⏳ ~14 days** |

### Field Coverage (live active listings, n=3,400)
| Field | jofogas (1,784) | otthonterkep (1,616) | Δ since 06-26 03:52 |
|-------|:----------:|:--------------:|:---:|
| price | 99.9% | 98.8% | — |
| area_sqm | 99.8% | 79.3% | ⬆ backfill adding data |
| rooms | 97.5% | 83.9% | ⬆ |
| listing_type | 100% | 99.0% | — |
| property_type | 100% | 98.6% | ⬆ |
| condition | 96.4% | 99.0% | — |
| heating | 96.9% | 58.7% | ⬆ (+12pp) |
| **year_built** | **9.7%** | **5.7%** | 🟡 low both sides |
| **listed_at** | **100%** | **0%** | ⚠️ SSR gap (needs Playwright) |
| lat/lng | 100% | 62.8% | ⬆ geocoding backlog |
| balcony_sqm | 97.6% | **0.2%** | ⚠️ SSR gap |
| **total_floors** | **10.9%** | **37.3%** | ✨ fixed in 005 |
| floor | **86.0%** | **0.0%** | jofogas fine, otthonterkep SSR |
| **plot_sqm** | **0%** | **14.0%** | ✨ new field (005) |
| seller_type | 100% | 99.0% | — |

---

## Databases

| Database | Host | Purpose |
|----------|------|---------|
| `real_estate_scraper` | 10.10.10.103:5432 | Scraped listings |
| `upwork_pipeline` | 10.10.10.103:5432 | Upwork score pipeline |

Connections via Vault dynamic credentials (`scraper-app` role, 1h lease) or static KV.

---

## Tables

| Table | Purpose | Rows |
|-------|---------|------|
| `raw_listings` | Staging — raw JSON per source | ~3,600 |
| `listings` | Canonical — 20+ parsed fields | 3,400 |
| `properties` | Golden records (consolidated entities) | 496 |
| `property_matches` | Cross-portal match candidates | 0 |
| `property_sources` | Links listings → properties | — |
| `price_history` | Price change tracking | (empty) |
| `city_coordinates` | GPS lookup for geocoded cities | 117 |

---

## Pipeline (Daily Cron)

**Schedule**: `0 5 * * *` (CET, via system crontab)

1. `scrape_jofogas.py --incremental` — listing-page sweep, skips existing URLs  
2. `scrape_otthonterkep.py --incremental` — sitemap crawl  
3. `refresh_listings()` — PL/pgSQL parses raw JSON → canonical listings  
4. `refresh_consolidation()` — PL/pgSQL entity resolution  

Logs: `/tmp/realestate-cron.log`

---

## Source Details

### jofogas.hu 🟢 (SSR JSON)
- **Method**: `requests` → listing page pagination `/{lakas,haz,garazs}?o=N`
- **Data**: `__NEXT_DATA__` JSON → price, parameters, GPS, images, listed_at
- **Market**: ~5K lakás (201 pg), ~940 ház (38 pg), ~90 garázs (4 pg) = **~6,000 active**
- **v6**: Listing-page sweep (replaces broken sitemap). Incremental mode. Sorted newest-first.

### otthonterkep.hu 🟢 (SSR HTML)
- **Method**: `requests` → sitemap XML (3 parts, ~73K URLs) → listing pages
- **Data**: `page_data` JSON + `bootstrap_grid` + `property_summary` + `jsonld` (org-level only)
- **GPS**: Nominatim geocoding via `city_coordinates` lookup table
- **96% live**: 48/50 sampled sitemap URLs redirect 200 → valid listing
- **Incremental**: `--incremental` skips existing URLs via DB query before sitemap fetch

### ingatlan.com 🛑 (NOT SCRAPED)
- **Legal**: ToS explicitly prohibits scraping (clauses 9.4.8, 9.4.9, 9.4.10)
- **Technical**: Cloudflare Enterprise + Distil Networks anti-bot
- **Status**: Scoped out permanently.

---

## Key Files

| Path | Purpose |
|------|---------|
| `src/scrape_jofogas.py` | Dumb collector: listing-pages → `__NEXT_DATA__` JSON (v6) |
| `src/scrape_otthonterkep.py` | Dumb collector: sitemap → SSR JSON (v5, `--incremental`) |
| `src/db.py` | Minimal: `get_conn()` + clean_* helpers |
| `src/pii_filter.py` | Regex-based PII removal before DB insert |
| `src/daily_pipeline.py` | Orchestrator: scrape → parse → consolidate |
| `src/vault_creds.py` | Vault dynamic credential helper (scraper-app role) |
| `daily_pipeline.sh` | Shell wrapper for cron invocation |
| `migrations/001_raw_listings.sql` | raw_listings staging + PL/pgSQL parse functions |
| `migrations/002_consolidation_layer.sql` | Properties + entity resolution |
| `migrations/003_city_geocode.sql` | City geocoding + HU→EN property_type |
| `migrations/004_analytics_views.sql` | Field coverage, price stats, city views |
| `migrations/005_parser_fixes.sql` | total_floors, plot_sqm, area cap, overflow guards |
| `PLAN.md` | Full implementation log (historical) |
| `SCRAPING_PLAN.md` | Original reconnaissance & legal analysis |

---

## Changelog

### 2026-06-26 — otthonterkep Backfill + Parser Overhaul
- **otthonterkep `--incremental`**: New mode skips existing URLs — 73K total, only fresh scraped  
- **Backfill launched**: 5K listings (~45/min, ~73 min runtime)  
- **Parser fix 005**: Belső szintek → total_floors (was floor — 603 records vs 0)  
- **Parser fix 005**: TERÜLET → plot_sqm (recovered 227 records)  
- **area_sqm cap**: 5–5000 m² sanity filter (rejects plot-sized bogus values)  
- **price_per_sqm guard**: Cap at 10M HUF/sqm to avoid NUMERIC overflow  
- **Column widening**: price_per_sqm NUMERIC(8,1)→12,1, area_sqm→10,1, plot_sqm→12,1  
- **daily_pipeline.py**: uses `--incremental` for otthonterkep  
- **Git**: 9 commits pushed (main@505e2ae)

### 2026-06-25 — jofogas v6 + Field Coverage Audit
- **jofogas v6**: Listing-page sweep replaces broken sitemap. 63× more URLs (96→6,000).  
- **Parser fixes**: floor_count→total_floors (0%→38%), building_date→year_built (0%→12%)  
- **Incremental mode**: `--incremental` flag for daily runs  
- **Vault creds**: Dynamic PG roles wired into all scripts  

### 2026-06-24 — Architecture Reset
- Dumb collectors + PL/pgSQL parsing architecture  
- Consolidation layer (migrations 002-003)  
- PII filter, GPS geocoding, pgadmin fix  

---

## Remaining TODOs

### Pipeline
- [ ] **otthonterkep acceleration**: 5K/day target → completes ~14 days *(backfill running)*
- [ ] **Resume jofogas backfill**: ~4,200 remaining (process crashed at 606)
- [ ] **New listing discovery**: Daily jofogas listing page diff

### Data quality
- [ ] **Fix listed_at for otthonterkep** (0% — SSR gap, needs Playwright)
- [ ] **Fix balcony_sqm for otthonterkep** (0.2% — SSR gap)
- [ ] **Fix heating for otthonterkep** (58.7% — improving with data)
- [ ] **Fix year_built for both** (~7-9% — low coverage)
- [ ] **GPS geocoding for otthonterkep** (62.8% — backfill adding unmatched cities)

### Upstream
- [ ] **Entity resolution** — cross-portal dedup after full inventory
- [ ] **Auto-confirm thresholds** — tune property_matches scoring

---

## Git

```text
origin	git@github.com:mandras81/hu-real-estate-scraper.git (fetch)
origin	git@github.com:mandras81/hu-real-estate-scraper.git (push)
```
