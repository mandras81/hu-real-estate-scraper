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

# Full backfill (all ~6K jofogas)
python3 src/scrape_jofogas.py 6000
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

## Current State (2026-06-26 03:52 UTC)

| Source | Active Market | Collected | Strategy | Time to Full |
|--------|:------------:|:--------:|----------|:-----------:|
| **jofogas** | ~6,000 (lakás+ház+garázs) | **893** | Listing page sweep `/{cat}?o=N` + incremental | ✔ Backfill running |
| **otthonterkep** | ~70,000 (96% live) | 199 | Sitemap crawl 5K/day | ~14 days |
| **Total** | **~76,000** | **1,092** | Polite daily pipeline | **~14 days** |

### Field Coverage (live, n=1,092)
| Field | jofogas (893) | otthonterkep (199) | Notes |
|-------|:--------:|:----------:|-------|
| price | 892 (99.9%) | 199 (100%) | ✅ |
| area_sqm | 890 (99.7%) | 192 (96.5%) | ✅ |
| rooms | 849 (95.1%) | 137 (68.8%) | 🟡 medium |
| listing_type | 893 (100%) | 192 (96.5%) | ✅ |
| property_type | 893 (100%) | 189 (95.0%) | ✅ |
| condition | 842 (94.3%) | 192 (96.5%) | ✅ |
| heating | 844 (94.5%) | 92 (46.2%) | 🟡 medium |
| **year_built** | **71 (8.0%)** | **26 (13.1%)** | 🔴 broken |
| **listed_at** | **893 (100%)** | **0 (0%)** | 🔴 otthonterkep broken |
| lat/lng | 893 (100%) | 192 (96.5%) | ✅ |
| balcony_sqm | 851 (95.3%) | 2 (1.0%) | 🟡 medium |
| **total_floors** | **195 (21.8%)** | **0 (0%)** | 🔴 otthonterkep missing |
| floor | 645 (72.2%) | 35 (17.6%) | 🟡 medium |
| seller_type | 893 (100%) | 192 (96.5%) | ✅ |

### Listing Types
| Type | Count | % |
|------|-------|---|
| sell | ~920 | ~84% |
| rent | ~140 | ~13% |
| NULL | ~32 | ~3% |

### raw_listings staging: ~1,100 rows

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
| `raw_listings` | Staging — raw JSON per source | ~1,100 |
| `listings` | Canonical — 20+ parsed fields | 1,092 |
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
- **Data**: `__NEXT_DATA__` JSON → product price, parameters, GPS, images, listed_at
- **Market**: ~5K lakás (201 pg), ~940 ház (38 pg), ~90 garázs (4 pg) = **~6,000 active**
- **v6 Update**: Replaced broken sitemap with real listing-page sweep. Incremental mode. Sorted newest-first.

### otthonterkep.hu 🟢 (SSR HTML)
- **Method**: `requests` → sitemap XML (3 parts) → listing pages → page_data JSON + bootstrap_grid
- **GPS**: Nominatim geocoding via `city_coordinates` lookup table
- **Sitemap**: ~75K URLs at `new.ingatlantajolo.hu/sitemap/`, 96% live
- **Fixes needed**: `listed_at` (SSR, date extraction), `balcony_sqm`, `heating` coverage

### ingatlan.com 🛑 (NOT SCRAPED)
- **Legal**: ToS explicitly prohibits scraping (clauses 9.4.8, 9.4.9, 9.4.10)
- **Technical**: Cloudflare Enterprise + Distil Networks anti-bot
- **Status**: Scoped out permanently.

---

## Key Files

| Path | Purpose |
|------|---------|
| `src/scrape_jofogas.py` | Dumb collector: listing-pages → `__NEXT_DATA__` JSON (v6) |
| `src/scrape_otthonterkep.py` | Dumb collector: sitemap → SSR JSON (v5) |
| `src/db.py` | Minimal: `get_conn()` + clean_* helpers |
| `src/pii_filter.py` | Regex-based PII removal before DB insert |
| `src/daily_pipeline.py` | Orchestrator: scrape → parse → consolidate |
| `src/vault_creds.py` | Vault dynamic credential helper (scraper-app role) |
| `daily_pipeline.sh` | Shell wrapper for cron invocation |
| `migrations/001_raw_listings.sql` | raw_listings staging + PL/pgSQL parse functions |
| `migrations/002_consolidation_layer.sql` | Properties + entity resolution |
| `migrations/003_city_geocode.sql` | City geocoding + HU→EN property_type |
| `PLAN.md` | Full implementation log (historical) |
| `SCRAPING_PLAN.md` | Original reconnaissance & legal analysis |

---

## Changelog (recent)

### 2026-06-25
- **jofogas v6**: Listing-page sweep replaces broken sitemap. 63× more URLs (96→6,000).
- **Parser fixes**: `floor_count`→`total_floors` (0%→38%), `building_date`→`year_built` (0%→12%)
- **Incremental mode**: `--incremental` flag for daily runs
- **Vault creds**: Dynamic PG roles wired into all scripts

### 2026-06-24
- Architecture reset: dumb collectors + PL/pgSQL parsing
- Consolidation layer (migrations 002-003)
- PII filter, GPS geocoding, pgadmin fix

---

## Remaining TODOs

### Pipeline
- [ ] **otthonterkep acceleration**: Bump to 5K/day → completes ~14 days
- [ ] **Resume jofogas backfill**: ~5,400 remaining (process crashed at 606)
- [ ] **New listing discovery**: Daily jofogas listing page diff

### Data quality
- [ ] **Fix listed_at for otthonterkep** (0% — SSR date extraction needed)
- [ ] **Fix balcony_sqm for otthonterkep** (1% — property_summary)
- [ ] **Fix total_floors for otthonterkep** (0% — bootstrap grid)
- [ ] **Fix floor for otthonterkep** (17.6% — property_summary)
- [ ] **Fix heating for otthonterkep** (46.2% — bootstrap grid)
- [ ] **Fix year_built for jofogas** (8% — building_date only partial)

### Upstream
- [ ] **Analytics views** — price trends, city coverage, field completeness
- [ ] **Auto-confirm improvements** — entity resolution thresholds
- [ ] **Entity resolution** — cross-portal dedup after full inventory
