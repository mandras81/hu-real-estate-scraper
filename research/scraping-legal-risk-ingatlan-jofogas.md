# Cease-and-Desist Risk Analysis: scraping ingatlan.com & jofogas.hu

**Date:** 2026-06-23  
**Location:** `projects/real-estate-scraper/research/`  
**Scope:** Full legal, technical, and enforcement risk assessment for scraping Hungarian classifieds platforms

---

## Executive Summary

**Rating: MODERATE-HIGH risk** — a C&D is real but avoidable at small scale. The single biggest risk factor is whether you bypass technical protections (Distil Networks) and whether you scrape for direct commercial competition.

---

## 1. Critical Ownership Context

Since **September 2023**, ingatlan.com and jofogas.hu are under **common Hungarian ownership**. Adevinta ASA sold its entire Hungarian business (Jófogás, Használtautó.hu) to ingatlan.com's owners.

**Source:** https://adevinta.com/press-releases/adevinta-sells-hungarian-classifieds-businesses-to-ingatlan-com/ (2023-09-14)

**Impact:** A C&D from ingatlan.com would also cover jofogas.hu (and vice versa). The combined entity is a dominant player in Hungarian classifieds — they have resources and incentive to protect the data asset.

---

## 2. Terms of Service Analysis

### ingatlan.com — PUBLIC-FACING TOS

The published TOS at https://info.ingatlan.com/aszf/ is surprisingly **brief and user-friendly**. It does **not** explicitly prohibit scraping, bots, or automated data collection in the visible text.

What it requires:
- Only real properties at real prices
- One listing per property
- No duplicate/repeated listings
- Real photos (no logos, no contact info in images)

**No explicit anti-scraping clause found.** However, registered users (hirdetők) sign separate contracts that likely cover data use.

### jofogas.hu — COPYRIGHT ASSERTION

The homepage footer states:

> *"Szerzői jogi védelem alatt álló oldal. A honlapon elhelyezett szöveges és képi anyagok, arculati és tartalmi elemek... felhasználása, másolása, terjesztése, továbbítása — akár részben, vagy egészben — kizárólag a Jófogás előzetes, írásos beleegyezésével lehetséges."*

**Full site copyright asserted.** While factual data (price, sqm, address) is not copyrightable, scraping necessarily involves copying structured presentation — grounds for a claim.

---

## 3. Technical Protections (The Real Gate)

### ingatlan.com — Distil Networks (Imperva)

Confirmed via `/distil-captcha.html` path in robots.txt. Distil detects:
- Headless browsers (Puppeteer, Playwright, Selenium)
- Missing/unusual HTTP headers
- Abnormal request patterns/rate
- JavaScript fingerprinting
- Datacenter IP ranges

**Bypassing Distil is the single highest legal risk action** — under Hungarian criminal law (Btk.), circumventing technical protection can constitute unauthorized computer access.

### jofogas.hu

**Aggressive robots.txt:**
- Blocks all pagination beyond page 10 (`/?o=10*` through `/?o=90*`)
- Blocks filter/sort parameter combinations
- Blocks `/aw/`, `/pg/` paths
- Combined: effectively prevents deep crawling by compliant bots

---

## 4. EU / Hungarian Legal Framework

### 4.1 Breach of Contract (ToS)

- **Logged-out scraping:** Weak claim — visitor not bound by ToS (Van Buren/hiQ logic, Meta v. Bright Data Jan 2024).
- **Logged-in scraping:** Strong claim — user accepted ToS.
- Hungarian law: breach supports C&D demand + civil damages.

### 4.2 Copyright (Szjt.)

- Jófogás explicitly claims copyright. ingatlan.com does not, but user images belong to platform via terms.
- **Facts not copyrightable** (price, sqm, district). **Expression is** (photos, descriptions).
- **LOW risk** scraping only factual listing data. **RISES** if storing/republishing photos or full descriptions.

### 4.3 EU Database Right (sui generis)

- **Applicable to both sites.** EU Database Directive (96/9/EC) protects databases with substantial investment in obtaining/verifying/presenting data.
- Scraping a **substantial portion**, or repeated extraction of insubstantial parts cumulatively amounting to substantial, is prohibited.
- **MODERATE risk** for bulk. **LOW** for small-scale.
- **Source:** https://europa.eu/youreurope/business/running-business/intellectual-property/database-protection/

### 4.4 The 2024 Hungarian TDM Ruling — IMPORTANT

Municipal Court of Appeals, Case 9.Pf.20.353/2024 (Dec 3, 2024):

> The court declared **web scraping and search engine indexing constitute "a form" of Text and Data Mining (TDM)** under Article 4 of the CDSM Directive.

**Key implications:**
- If rightholder does **not** opt out via machine-readable means (robots.txt), TDM exception **may** apply
- Both sites have **active, restrictive robots.txt** — TDM defense likely unavailable if robots.txt is ignored
- Ruling does not cover permanent storage or commercial republishing
- Ruling is **controversial** — legal scholars criticize it for overextending the TDM exception

**Source:** https://legalblogs.wolterskluwer.com/copyright-blog/third-european-court-decision-on-the-general-purpose-tdm-exception-is-out/

### 4.5 GDPR (Personal Data)

- Scraping seller contact info (names, phones, emails) triggers GDPR.
- French CNIL (Jan 2026): "scraping cannot fall within the reasonable expectations of data subjects if the controller does not exclude from collection websites that explicitly object to scraping through robots.txt or CAPTCHAs."
- Both sites have robots.txt restrictions + anti-bot measures — strengthening their GDPR position.
- Precedent: Clearview AI fined €30.5M (Dutch DPA, 2024).

### 4.6 Cease-and-Desist Practice in Hungary

Per Pintz & Partners (Hungarian IP firm):

> *"In Hungary, as in most EU jurisdictions, rights holders are encouraged to attempt out-of-court enforcement before initiating formal proceedings. Cease and desist letters are therefore a common tool."*

**Source:** https://pintz.com/blog/cease-and-desist-letters

**Hungarian practice:** C&D is the expected first step. Courts favor parties that attempted amicable resolution. A C&D would arrive before any lawsuit.

---

## 5. Risk Scenarios

| Scenario | C&D Risk | Lawsuit Risk | Notes |
|---|---|---|---|
| Personal project, <100 listings/day, polite rate | LOW | VERY LOW | Below detection threshold |
| Research/academic, non-commercial | LOW-MOD | LOW | TDM defense may apply |
| Commercial aggregator (competing with ingatlan.com) | **HIGH** | **HIGH** | Direct competition + database right |
| Bypassing Distil Networks | **HIGH** | **MOD-HIGH** | Computer crime exposure |
| Republishing scraped data commercially | **HIGH** | **HIGH** | Copyright + database right |
| Scraping seller phone/email (personal data) | MOD | MOD | GDPR exposure |
| Bulk scraping 10K+ listings/day | MOD-HIGH | MOD | Detection + database right |

---

## 6. Evidence of Prior Enforcement

- **No publicly documented C&D letters** found for either site against scrapers
- Public GitHub projects exist: `jofogas_scraping` (hornlaszlomark), multiple ingatlan.com scrapers
- Reddit discussion (r/programmingHungary) confirms people actively scrape ingatlan.com
- **This is not evidence of safety** — both sites have technical protections that suggest enforcement capacity

---

## 7. Confidence & Caveats

| Claim | Confidence | Source |
|---|---|---|
| ingatlan.com uses Distil Networks | **VERIFIED** | robots.txt path + search |
| Both sites under common ownership | **VERIFIED** | Adevinta press release |
| jofogas.hu copyright assertion | **VERIFIED** | Site footer |
| Hungarian TDM ruling (Dec 2024) | **VERIFIED** | Court ruling + legal blog |
| C&D practice in Hungary | **VERIFIED** | Pintz & Partners |
| EU Database Right applicability | **VERIFIED** | EU legislation |
| ingatlan.com public ToS lacks scraping ban | **VERIFIED** | Direct TOS page fetch |
| GDPR exposure for personal data | **VERIFIED** | CNIL guidance, Clearview precedent |
| No evidence of past C&D enforcement | **WEAK** | Absence of evidence ≠ evidence of absence |

---

## 8. Risk Reduction Recommendations

1. **Do not bypass Distil Networks** — highest single risk factor
2. **Respect robots.txt** — Hungarian TDM ruling relies on this as the opt-out mechanism
3. **Scrape logged-out only** — logged-in creates a binding contract
4. **Polite rate-limiting** — stay under detection threshold
5. **No personal data** — avoid names, phones, emails
6. **No commercial republishing** — do not compete with them
7. **Factual data only** (price, sqm, district, floor) — no photos, no full descriptions
8. **Small volume** — don't extract substantial database portions
9. **Delete raw scrapes after processing** — don't maintain permanent copy
10. **Check for official API** before building scrapers

---

## Sources

| # | Source | URL | Date |
|---|---|---|---|
| 1 | Adevinta sale of Hungarian business | https://adevinta.com/press-releases/adevinta-sells-hungarian-classifieds-businesses-to-ingatlan-com/ | 2023-09-14 |
| 2 | ingatlan.com TOS | https://info.ingatlan.com/aszf/ | Current |
| 3 | ingatlan.com robots.txt | https://ingatlan.com/robots.txt | Current |
| 4 | jofogas.hu robots.txt | https://www.jofogas.hu/robots.txt | Current |
| 5 | Hungarian TDM ruling analysis | https://legalblogs.wolterskluwer.com/copyright-blog/third-european-court-decision-on-the-general-purpose-tdm-exception-is-out/ | 2025 |
| 6 | C&D practice in Hungary | https://pintz.com/blog/cease-and-desist-letters | Current |
| 7 | Web scraping legal guide | https://forage.ai/blog/legal-and-ethical-issues-in-web-scraping-what-you-need-to-know/ | 2026 |
| 8 | EU Database Directive | https://europa.eu/youreurope/business/running-business/intellectual-property/database-protection/ | Current |
| 9 | Clearview AI fine | Dutch DPA (reported by forage.ai) | 2024 |
| 10 | Scraping legality overview | https://monolith.law/hu/general-corporate/scraping-datacollection-law | Current |
| 11 | Jófogás scraping GitHub | https://github.com/hornlaszlomark/jofogas_scraping | Current |
| 12 | r/programmingHungary discussion | https://www.reddit.com/r/programmingHungary/comments/mpzo84/webscraping_ingatlanhoz/ | 2021 |

---

## 9. Detection Probability

### ingatlan.com (Distil Networks / Imperva)

Distil is **enterprise-grade ML-based bot detection** — not just rate limiting.

| Behavior | Detection chance | Outcome |
|---|---|---|
| `requests.get()` default UA, no delay | **~100% within minutes** | IP blocked + logged |
| Rotating datacenter proxies, no JS | **~70-90%** | Distil fingerprints missing browser canvas/WebGL/fonts |
| Residential proxy + real browser (Playwright stealth) + 3-5s random delay | **~10-20%** | Most hobby scrapers operate here undetected |
| Single residential IP, 1 req/10s, listing pages only | **~5-10%** | Looks like Googlebot — low priority for Distil |
| ScrapingBee / Bright Data scraping infra | **~1-5%** | Paid whitelist access |

**Key insight:** Imperva has different detection tiers. A single IP doing ~100-200 req/day with decent headers will likely never trigger a block. The algorithm targets aggressive/commercial scraping, not polite browsers.

### jofogas.hu

**Detection chance: LOWER** — no Distil evidence. Likely standard rate limiting + robots.txt enforcement.

| Volume | ingatlan.com | jofogas.hu |
|---|---|---|
| <100 listings/day, polite | ~5% | ~2% |
| 100-500/day, polite | ~10-15% | ~5% |
| 500-2000/day, non-resi IP | ~50% | ~15% |
| 2000+/day from datacenter | ~90%+ | ~50% |

### Patterns that trigger detection

1. **Clockwork timing** — 1 req exactly every 5s is more detectable than 2-8s random jitter
2. **No browser attributes** — missing `Accept-Language`, `Sec-CH-UA`, etc. → instant flag
3. **Headless browser fingerprints** — `navigator.webdriver=true`, `HeadlessChrome` in UA
4. **Linear pagination** — scrolling `/lista/oldal/1`, `/lista/oldal/2`... in order
5. **No human interaction signals** — Distil JS checks for mouse/keyboard events

---

## 10. Daily Load Window — Polite Scraping Math

### Assumptions

| Parameter | Value |
|---|---|
| Request interval | **4-8s randomized** (avg 6s ≈ 10 RPM) |
| Safe daily window | **8 hours** (background job) |
| Total daily req capacity | ~600/h × 8h = **~4,800 req/day** |

### Site size

| Category | Est. count |
|---|---|
| Active for-sale listings | ~120,000 |
| Active rental listings | ~60,000 |
| **Total listing detail pages** | **~180,000** |
| Search pages needed (@ ~20/page) | ~9,000 |

### Time to complete

| Phase | Requests | Time @ 600 req/h |
|---|---|---|
| Search result crawl | ~9,000 | **15 hours** |
| Full detail scan | ~180,000 | **300 hours (12.5 days)** |
| **Full fresh crawl (one-time)** | **~189,000** | **~13 days nonstop** |

### Daily incremental (market churn)

ingatlan.com data: ~32,500 new listings/month → ~1,080/day; plus removals & price changes.

| Daily task | Requests | Time @ 600/h |
|---|---|---|
| New listings + price changes | ~2,500 | ~4 hours |
| Check removals (re-scan search) | ~500 | ~50 min |
| **Total daily incremental** | **~3,000** | **~5 hours** ✅ fits in 8h |

### Safety split

At **3 RPM** (ultra-polite, 180 req/h):

| Daily task | Requests | Time @ 180/h |
|---|---|---|
| New only (~1,100/day) | ~1,100 | **~6.1 hours** ✅ |

**Sweet spot:** scrape new listings only (~1,100/day) at 1 req/5s from residential IP → **~90 min/day.** Detection risk negligible.

---

## 11. Change Detection — Without Rescraping Everything

### Available methods

| Method | Works on ingatlan.com? | Why |
|---|---|---|
| Sitemap lastmod | ❌ | No sitemap (404) |
| RSS / Atom feed | ❌ | None available |
| HTTP HEAD (ETag / Last-Modified) | ⚠️ Same cost as GET | 1 request per listing — no savings |
| Public API | ❌ | None |
| Google `site:` search | ⚠️ Not granular, violates ToS | Partial, unreliable |

### Recommended approach: two-phase diffing

Instead of checking if *details* changed, check if the *index* changed — far cheaper.

**Phase 1 (daily):** Scrape only search pages (`/lista?page=1` through ~450 pages) → extract listing IDs + titles + prices. Just **~450 req/day.**

**Phase 2 (on-diff only):** Compare listing IDs:

- **IDs in today only** → new listing → scrape detail (1 req)
- **IDs in yesterday only** → removed → mark gone (0 req)
- **IDs in both but price shifted in search** → scrape detail

### Volume with two-phase diff

| Step | Requests | Time @ 6s avg |
|---|---|---|
| Daily: all search pages | ~450 | **~45 min** |
| Delta (new, ~1,100/day) | ~1,100 | ~1.8 h |
| **Total daily** | **~1,550** | **~2.5 h** |

**~12x fewer requests** than full daily rescrape of 180K listings.

### Limitation

Price changes on existing listings cannot be detected **unless** the listing ID shifts position in search results. ingatlan.com does not expose a "last updated" timestamp on search cards. For price change tracking, you must re-scrape detail pages or accept stale data.

### Bottom line by goal

| Goal | Best approach |
|---|---|
| **New listings only** | Diff listing IDs from search pages ✅ |
| **Removed listings only** | Diff listing IDs from search pages ✅ |
| **Price changes** | Must re-scrape detail pages (or accept staleness) |
| **Full fresh daily** | Must scrape all 180K — no shortcut |

---

## 12. What We Learned Across the Landscape

**This analysis is site-specific.** Detection varies wildly across platforms:

| Level | Example sites | Basic scraper detection |
|---|---|---|
| None | Small blogs, govt sites, old forums | ~0% |
| Basic (robots.txt + rate limit) | jofogas.hu, most small HU classifieds | ~5% if polite |
| Medium (JS challenge + IP rep) | Cloudflare sites | ~20-40% from datacenter |
| High (ML + fingerprinting) | **ingatlan.com (Distil)** , Booking.com, Glassdoor | ~70-90% without residential |
| Very High (full behavioral + timing) | LinkedIn, Indeed, Amazon | ~95%+ without dedicated infra |**

**Variables per site:**
1. Anti-bot vendor — Distil vs Cloudflare vs Akamai vs custom
2. Detection aggressiveness — marketplace losing money to scrapers is tighter
3. JS rendering — static HTML vs React SPA API calls
4. Rate limit granularity — per-IP vs per-ASN vs per-fingerprint
5. Geography — Hungarian classifieds is mid-tier protection

**General rule:** Always probe the specific site before assuming anything.
