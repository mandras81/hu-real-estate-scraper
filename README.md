# Real Estate Scraper — Hungarian Property Pipeline 🇭🇺🏠

Dumb HTTP scrapers → PostgreSQL → PL/pgSQL parsing → entity resolution.

**Scope**: Hungarian real estate portals only (jofogas.hu, otthonterkep.hu).  
**Architecture**: Scrapers are zero-business-logic HTML→JSON collectors. All parsing in SQL.

---

## Quick Start

```bash
# 1. Run daily pipeline (200 listings per source)
./daily_pipeline.sh 200

# 2. Or step by step
python3 src/scrape_jofogas.py 200
python3 src/scrape_otthonterkep.py 200

# 3. After scraping: refresh canonical listings
#    (runs automatically in daily_pipeline.py)
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

## Current State (2026-06-25 — Audit Update)

| Source       | Active Market | Collected | Strategy | Time to Full |
|--------------|:------------:|:--------:|----------|:-----------:|
| **jofogas**  | ~6,000 (lakás+ház+garázs) | 276 | Listing page sweep (`/{cat}?o=N`) | ~1 day |
| **otthonterkep** | ~70,000 (96% of 73K live) | 199 | Sitemap crawl 5K/day | ~14 days |
| **Total**    | **~76,000** | **475** | Polite daily pipeline (~2.5h) | **~14 days** |

### Field Coverage (% non-null)
| Field | jofogas (276) | otthonterkep (199) | Notes |
|-------|:--------:|:----------:|-------|
| price | 99.6% | 100% | ✅ |
| area_sqm | 99.3% | 96.5% | ✅ |
| rooms | 86.6% | 68.8% | 🟡 |
| condition | 88.8% | 96.5% | ✅ |
| **year_built** | **0%** | **13.1%** | 🔴 broken |
| heating | 88.4% | 46.2% | 🟡 |
| **listed_at** | **100%** | **0%** | 🔴 broken |
| lat/lng | 100% | 96.5% | ✅ |
| balcony_sqm | 88.4% | 1% | 🟡 |
| **total_floors** | **0%** | **0%** | 🔴 missing |
| floor | 44.2% | 17.6% | 🟡 |

### Listing Types
| Type | Count |
|------|-------|
| sell | 320 |
| rent | 52 |
| NULL | 7 |

### raw_listings staging: 423 rows

---

## Databases

| Database | Host | Purpose |
|----------|------|---------|
| `real_estate_scraper` | 10.10.10.103:5432 | Scraped listings |
| `upwork_pipeline` | 10.10.10.103:5432 | Upwork score pipeline |

---

## Tables

| Table | Purpose | Rows |
|-------|---------|------|
| `raw_listings` | Staging — raw JSON per source | 423 |
| `listings` | Canonical — 20+ parsed fields | 379 |
| `properties` | Golden records (consolidated entities) | 400 |
| `property_matches` | Cross-portal match candidates | 0 |
| `property_sources` | Links listings → properties | — |
| `price_history` | Price change tracking | (empty) |
| `city_coordinates` | GPS lookup for geocoded cities | 117 |

---

## Pipeline (Daily Cron)

**Schedule**: `0 5 * * *` (CET, via system crontab)

1. `scrape_jofogas.py` — fetches sitemap, extracts `__NEXT_DATA__` → raw_listings
2. `scrape_otthonterkep.py` — fetches sitemap, extracts SSR JSON → raw_listings
3. `refresh_listings()` — PL/pgSQL: parses raw → upserts into listings
4. `refresh_consolidation()` — PL/pgSQL: cross-portal entity resolution

Logs: `/tmp/realestate-cron.log`

---

## Source Details

### jofogas.hu 🟢 (SSR JSON)
- **Method**: `requests` → sitemap XML → listing pages → `__NEXT_DATA__` JSON
- **Data**: product price, parameters (city/area/rooms/condition/heating/year_built), GPS, images
- **Pagination**: Sitemap XML at `?o={0..16000}` (2000 URLs/page)

### otthonterkep.hu 🟢 (SSR HTML)
- **Method**: `requests` → sitemap XML → listing pages → page_data JSON + bootstrap_grid + jsonld
- **GPS**: Nominatim geocoding via `city_coordinates` lookup table
- **Sitemap**: 3 parts at `new.ingatlantajolo.hu/sitemap/`, ~75K total URLs

### ingatlan.com 🛑 (NOT SCRAPED)
- **Legal**: ToS explicitly prohibits scraping (clauses 9.4.8, 9.4.9, 9.4.10)
- **Technical**: Cloudflare Enterprise + Distil Networks anti-bot
- **Status**: Scoped out. Not part of this pipeline.

---

## Key Files

| Path | Purpose |
|------|---------|
| `src/scrape_jofogas.py` | Dumb collector: HTML → raw JSON via `__NEXT_DATA__` |
| `src/scrape_otthonterkep.py` | Dumb collector: HTML → raw JSON via SSR |
| `src/db.py` | Minimal: `get_conn()` + clean_* helpers |
| `src/pii_filter.py` | Regex-based PII removal before DB insert |
| `src/daily_pipeline.py` | Orchestrator: scrape → parse → consolidate |
| `daily_pipeline.sh` | Shell wrapper for cron invocation |
| `migrations/001_raw_listings.sql` | raw_listings staging + parse functions |
| `migrations/002_consolidation_layer.sql` | Properties table + entity resolution |
| `migrations/003_city_geocode.sql` | City geocoding + HU→EN property_type mapping |
| `PLAN.md` | Full implementation log (historical) |
| `SCRAPING_PLAN.md` | Original reconnaissance & legal analysis |

---

## Remaining TODOs

### Pipeline
- [ ] **jofogas rewrite**: Listing-page scraping (`/{lakas,haz,garazs}?o=N`) instead of sitemap
- [ ] **otthonterkep acceleration**: Bump to 5K/day → completes ~14 days
- [ ] **New listing discovery**: Daily jofogas listing page diff

### Data quality
- [ ] **Fix year_built** (0% both — parser bug)
- [ ] **Fix listed_at for otthonterkep** (0% — SSR date extraction)
- [ ] **Fix balcony_sqm for otthonterkep** (1% — property_summary)
- [ ] **Fix total_floors** (0% both)
- [ ] **Fix district** (0% both)
- [ ] **Fix floor** (44%/18%)
- [ ] **Fix heating** (88%/46%)

### Upstream
- [ ] **Analytics views** — price trends, city coverage, field completeness
- [ ] **Git push** — remote
- [ ] **Auto-confirm improvements** — adjust thresholds
- [ ] **Entity resolution** — cross-portal dedup after full inventory