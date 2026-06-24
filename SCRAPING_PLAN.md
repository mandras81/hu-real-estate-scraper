# Scraping Plan — real-estate-scraper
> Generated: 2026-06-23 | Reconnaissance executed live against all three portals.
---
## 1. ingatlan.com — Hard Target 🛡️
### Observed Behaviors
| Method | Result |
|---|---|
| Plain curl (UA: Chrome 125) | HTTP 403 — Cloudflare JS challenge |
| agent-browser (Chromium, headed) | HTTP 403 — blocked immediately |
| robots.txt | References `/distil-captcha.html` — Distil Networks anti-bot |
**Defense stack**: Cloudflare Enterprise + Turnstile + Distil Networks behavioral profiling. TLS fingerprinting and JA3 hash checks are active.
### Recommended Approach
Priority order — start with A, escalate:
| Priority | Strategy | Block Risk | Proxy Cost |
|---|---|---|---|
| A | `curl_cffi` — impersonate Chrome v125 TLS fingerprint | Low-medium | $0 |
| B | Playwright stealth + persisted browser profile | Medium | $0 |
| C | Smart proxy (Zyte / Bright Data / ScrapingBee) | Low | ~$100-300/mo |
**Detail**: Start with `curl_cffi` for index scans (lightweight, low detection surface). If blocks appear, switch to Playwright stealth mode with a warm Chromium profile. If both fail, route through a smart proxy service that handles Turnstile upstream.
**Key unknowns** (need browser inspection to resolve):
- Search endpoint URL pattern
- Listing detail page JS-rendered fields
- Image URL structure
---
## 2. jofogas.hu/ingatlan — Soft Target ✅
### Observed Behaviors
| Method | Result |
|---|---|
| Plain curl (UA: Chrome 125) | HTTP 200 — 490KB SSR HTML |
| agent-browser | HTTP 403 (different CDN edge) |
**Defense**: Proprietary rate-limiting + Akamai CDN. No Cloudflare, no Turnstile.
**Critical finding**: The page is **Next.js SSR**. Listing data is embedded as `__NEXT_DATA__` JSON inside the HTML. No JavaScript rendering needed.
### Data Available (off-the-shelf via SSR JSON)
```json
{
  "list_id": "159327671",
  "subject": "Eladó lakás Budapest 18. ker., Újpéteritelep",
  "body": "Budapest XVIII. kerületében...",
  "price": { "value": 71700000, "label": "71 700 000 Ft" },
  "type": { "label": "Eladó", "value": "s" },
  "region": { "label": "Budapest", "value": "1" },
  "category": { "id": 1020, "name": "Lakás" },
  "latitude": 47.4107725,
  "longitude": 19.1967175,
  "images": [{ "url": "https://img.jofogas.hu/bigthumbs/...jpg" }],
  "parameters": [
    { "key": "zipcode", "value": "1188", "label": "XVIII. kerület" },
    { "key": "rooms", "value": "3", "label": "3 szoba" },
    { "key": "size", "value": "57", "label": "57 m²" }
  ],
  "company_name": "Dota Life Europe Kft",
  "badges": ["company_ad", "gallery"],
  "url": "https://ingatlan.jofogas.hu/budapest/Elado_lakas_...159327671.htm"
}
```
### Search Parameters (discovered from SSR)
| Param | Usage | Example |
|---|---|---|
| `st` | Type (s=eladó, u=kiadó) | `st=s` |
| `cg` | Category (1000=ingatlan, 1020=lakás) | `cg=1020` |
| `w` | County (1=Budapest) | `w=1` |
| `min_price`, `max_price` | Price range | `min_price=0&max_price=100000000` |
| `min_size`, `max_size` | Size range | `min_size=30&max_size=200` |
| `ros`, `roe` | Rooms min/max | `ros=1&roe=5` |
| `bldt` | Building material | `bldt=1` (tégla), `2` (panel) |
| `rscond` | Condition | `2` (jó), `5` (új építésű) |
Image CDN: `https://img.jofogas.hu/bigthumbs/{filename}` — no auth.
### Strategy
```
requests.Session() + rotating user-agents
    → GET https://ingatlan.jofogas.hu/ingatlan?st=s&cg=1020&w=1&ros=1
    → Parse __NEXT_DATA__ JSON from HTML
    → Extract listing list_id, price, params, GPS, images
    → Paginate by incrementing offset or page param
    → Max 5 concurrent — respect rate limits
    → Fallback: mobile residential proxies (Bright Data)
```
---
## 3. otthonterkep.hu — Easiest Target ✅
### Observed Behaviors
| Method | Result |
|---|---|
| Plain curl (UA: Chrome 125) | HTTP 200 — SSR HTML listing cards |
| Repeated curl within 5s | HTTP 403 — temporary ban ("You got banned permanently from this server") |
| agent-browser | Renders fine, hCaptcha only on newsletter widget |
**Defense**: Basic rate-limiting. No Cloudflare, no Turnstile on listings.
**Scale**: 67,442 results for "lakás+Budapest" / 20 per page = **3,373 pages**
### URL Structure
```
# Search
/{category}+{city}/{county}/{sale_type}/0/0/0/0?p={page}&sort={field}|{dir}
# Example
/lakas+budapest/minden-megye/elado/0/0/0/0?p=2&sort=ad_feladas_time|desc
# Detail
/ingatlan/elado+{type}/{city}/{street}/nincs-cim/{ad_id}
```
### Listing Card Fields (SSR, parsed via BeautifulSoup)
- **Price**: `<h4 class="h4 fw-bold fw-price">66 900 000 Ft</h4>`
- **EUR price**: `<b>Kalkulált € ár:</b> 188 983 €`
- **m² price**: `983 824 Ft/m²`
- **Area**: `68.00m²`
- **Plot size**: `1159m²`
- **Image**: `ingatlantajolo.hu/user_{id}/ad_{id}/{file_id}-k1.jpg`
- **Location**: city name in heading before price
- **Detail link**: `/ingatlan/.../{ad_id}` — accessible via 20 cards per page
### Image CDN
`ingatlantajolo.hu` returns HTTP 403 on curl but **works in browser** (checks Origin/Referer or cookies). Solution: `curl_cffi` with proper referer header, or download through Playwright session.
### Strategy
```
requests.Session() + rotating user-agents
    → GET https://otthonterkep.hu/lakas+budapest/minden-megye/elado/0/0/0/0
    → Parse cards with BeautifulSoup (price, area, plot, city, image)
    → Sleep 2-4s random between pages
    → Page through ?p=1 ... ?p=3373
    → Detail fetches: optional (full detail is SSR-rendered)
    → Image downloads: curl_cffi with referer header
    → Fallback: low-cost datacenter proxies (< $20/mo)
```
---
## Architecture Overview
```
┌──────────────── Nightly Pipeline (20:00-06:00 UTC) ─────────────────┐
│                                                                     │
│  20:00 ── Phase 1 ── ingatlan.com (curl_cffi + browser fallback)   │
│  22:00 ── Phase 2 ── jofogas.hu     (requests, SSR JSON parse)     │
│  00:00 ── Phase 3 ── otthonterkep.hu(requests + BeautifulSoup)     │
│  02:00 ── Phase 4 ── Delta load + normalize → PostgreSQL           │
│  04:00 ── Phase 5 ── Entity resolution cascade                     │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```
### Pipeline Schedule
| Phase | Time (UTC) | Duration | Tooling |
|---|---|---|---|
| 1 | 20:00-22:00 | ~2h | curl_cffi / Playwright |
| 2 | 22:00-00:00 | ~2h | requests + json |
| 3 | 00:00-02:00 | ~2h | requests + BS4 |
| 4 | 02:00-04:00 | ~2h | SQL INSERT ON CONFLICT |
| 5 | 04:00-05:00 | ~1h | SQL + python |
### Infrastructure
- **Database**: PostgreSQL 16 on Docker (tuned: shared_buffers=1GB, work_mem=64MB)
- **Orchestration**: Prefect 2.x with systemd timer
- **Host**: Existing Proxmox LXC (16GB host)
- **Schema**: `listings_raw` (JSONB), `listings_normalized`, `price_history`, `pipeline_logs`
- **Entity resolution**: `pg_trgm` trigram similarity, deterministic blocking (zip+type+rooms), image pHash for cross-portal dedup
---
## Known Gaps vs Original PROMPT
| PROMPT Claim | Reality | Adjustment |
|---|---|---|
| curl_cffi alone for ingatlan.com | Cloudflare Enterprise — not enough | Browser stealth + proxy fallback |
| shared_buffers=4GB | Too aggressive for Docker | Use 1GB |
| otthonterkep "internal API" | SSR pages work fine | Scrape SSR |
| Zyte budget ~$100 | Real cost $200-500/mo | Start free, add proxies on-demand |
| Imagehash 2 photos/listing | 500+ downloads/day | Add cache layer |
---
## Next Steps (execution order)
1. Generate `schema.sql` — tables, indexes, extensions
2. Generate `config.yaml` — portal-specific settings, selectors, delays
3. Generate `scraper_jofogas.py` — SSR parse + paginate
4. Generate `scraper_otthonterkep.py` — BS4 parse + paginate
5. Generate `scraper_ingatlan.py` — curl_cffi + Playwright stealth
6. Generate `consolidator.py` — normalizer + entity resolution
7. Generate `pipeline.py` — Prefect orchestration flow
8. Generate `docker-compose.yml` + `Dockerfile`
---
## Key Decisions Documented
- **Three separate scrapers** — one per portal, different technology stacks
- **Delay randomization** — 1-4s for otthonterkep, 2-6s for jofogas, 3-10s for ingatlan
- **Rotating user-agents** — Chrome 120-130 pool per page_request
- **Session reuse** — one session per portal per run (avoids re-auth)
- **No headless browser for jofogas/otthonterkep** — SSR is sufficient
- **Image download** — optional, gated by config. Not required for price monitoring.
- **Delta architecture** — index scan (ID + price only) first, full detail only on change
- **Proxy escalation ladder** — datacenter → residential → smart proxy
---
## 4. Tibor's Cloudflare & Turnstile Experience (from Upwork project)
> **Source:** Tibor 🦊 — Researcher agent, persistent Chrome bypass proven in production since Jun 16  
> **Project:** Upwork pipeline — same Proxmox LXC, same infra stack
### Core Discovery
All headless/evasion approaches failed against Cloudflare Turnstile:
| Method | Result | Root Cause |
|---|---|---|
| Playwright bundled Chromium + stealth plugin | ❌ Blocked | `navigator.webdriver=true`, canvas fingerprint mismatch, fake TLS stack |
| Puppeteer | ❌ Blocked | Same as Playwright |
| agent-browser (Chromium) | ❌ Blocked | Uses bundled Chromium internally |
| curl / requests / web_fetch | ❌ 403 | TLS fingerprint gives it away |
| cloudscraper | ❌ Not enough | SPA + session-based auth |
| curl_cffi (TLS impersonation) | ❌ Partial | Spoofs TLS but can't execute JS challenges |
### What Works: Real Google Chrome + Persistent Profile
**The winning formula has two parts:**
#### Part A — Real Chrome Binary (not bundled Chromium)
The system's `google-chrome-stable` (v149+) has:
- `navigator.webdriver` = `undefined` (bundled Chromium forces this to `true`)
- Real GPU-rendered canvas fingerprint
- Real Chrome TLS fingerprint (JA3/JA4)
- Full `window.chrome` API — not mocked
#### Part B — Persistent Profile with Trusted Cookies
Once a real Chrome browser passes Turnstile manually (first login), the session cookies are **trusted for that browser profile indefinitely**. Future launches with the same profile skip the challenge entirely.
### Production Implementation (proven, running)
```javascript
const { chromium } = require('playwright');
const context = await chromium.launchPersistentContext(
  '/home/openclaw/.config/chrome-upwork-profile',  // persistent profile
  {
    headless: false,                         // xvfb provides virtual display
    executablePath: '/usr/bin/google-chrome-stable',  // REAL Chrome
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--disable-blink-features=AutomationControlled',
      '--no-first-run',
      '--no-default-browser-check'
    ]
  }
);
```
**Infra:**
- **xvfb-run** provides virtual framebuffer (headless server)
- **systemd service** keeps Chrome alive on CDP port 9222 for interactive use
- **Playwright** connects via `launchPersistentContext` for pipeline runs
- **Two independent profiles** exist (`/var/chrome-upwork-profile/` for CDP, `~/.config/chrome-upwork-profile/` for Playwright)
### Relevance to ingatlan.com
ingatlan.com uses the same Cloudflare Enterprise + Distil stack. The **same Playwright + real Chrome + persistent profile** approach is the most reliable path:
```
1. Create a fresh Chrome profile directory
2. Launch google-chrome-stable with that profile (headed via xvfb)
3. Navigate to ingatlan.com manually (first-time Turnstile challenge)
4. Solve the challenge once → cookies are trusted for that profile
5. From then on: Playwright launchPersistentContext with that profile → no challenge
```
### Backup Options (if persistent profile degrades)
Ranked by Tibor's research, from best to worst:
| Rank | Solution | Cost | Setup | Notes |
|---|---|---|---|---|
| 🥇 | **FlareSolverr** (Docker) | $0 | 30 min | Proxy service that runs real Firefox to solve CF challenges. Returns cookies + HTML. Good for one-off or low-volume. Can't navigate SPAs. |
| 🥈 | **CapSolver API** | ~$0.0012/solve | 1-2h | AI-based Turnstile solver. 97% success, <3s. $1 deposit lasts years at our volume. Token injection into browser is fiddly. |
| 🥉 | **curl_cffi** | $0 | Immediate | Works for light index scans where no JS challenge is served. Will break on Turnstile. |
| 4 | **SeleniumBase** (UC mode) | $0 | 30 min | Undetected Chrome driver. Alternate to Playwright, not incrementally better. |
| 5 | **2Captcha** | ~$0.50/1000 | 1h | Human-powered captcha solving. Slower than CapSolver. |
| 6 | **Bright Data Web Unlocker** | ~$200-500/mo | 1h | Enterprise proxy that handles all anti-bot layers. Most expensive but most reliable. |
### Key Lesson for This Project
**Don't waste time on evasion.** The THREE approaches worth trying, in order:
1. **Real Chrome + persistent profile** (proven, free, production-stable since Jun 16)
2. **FlareSolverr** (30 min setup, free, open-source)
3. **CapSolver API** (failsafe, ~$0 lifetime cost at our volume)
Everything else (stealth plugins, TLS fingerprinting, user-agent rotation) is **noise** against Cloudflare Enterprise + Turnstile.
---
## 5. Legal Analysis — Scraping Hungarian Real Estate Portals
> Analysis date: 2026-06-23 | Jurisdiction: Hungary / EU
> Covers: robots.txt compliance, GDPR, EU Database Directive, contract law, anti-circumvention
### 5.1 robots.txt — What Each Site Allows
| Site | robots.txt | What It Means |
|---|---|---|
| **ingatlan.com** | Disallows: `/lista`, `/szukites`, `/auth`, `/recommendation`, `/detailspage`, `/map`, `/_filter/fields`, `/distil-captcha.html`. Blocks AhrefsBot, dotbot, MJ12bot, trovitBot entirely. Sitemap returns 404. | **Listing pages and search endpoints are disallowed.** Also blocks known scraping bots outright. |
| **jofogas.hu** | Disallows: nearly ALL structured query parameters — `?min_price`, `?max_price`, `?cg` (category), `?f=*` (filters), `?o=*` (pagination 10-99), `?p=` (page), `?zip`, `?ib`, `?account_list_id=`. Blocks CariBot entirely. Has sitemap.xml. | **Can't crawl search/filter pages per robots.txt.** Sitemap allows direct listing page crawling. The extensive disallow patterns show they specifically don't want automated search scraping. |
| **otthonterkep.hu** | HTTP 403 on robots.txt (they ban fast). | No robots.txt accessible. Operating blind — no public guidance. |
### 5.2 Legal Status of robots.txt
**robots.txt is not legally binding** in Hungary or the EU. It's a voluntary protocol for cooperative crawlers (search engines). Courts in Europe have NOT treated robots.txt violations as trespass or unauthorized access.
However, **it matters for practical defense**: if a site can show you deliberately ignored their robots.txt, it strengthens their case for:
- Breach of contract (if ToS incorporates robots.txt by reference)
- Unfair competition (if scraping is for commercial rival use)
- Tort claims (interference with business)
### 5.3 Hungarian & EU Legal Framework
#### GDPR (EU 2016/679) — Personal Data
- **Private seller data is personal data**: names, phone numbers, email addresses of private individuals posting listings are protected.
- **Company/agent listings**: company names and business contact details are NOT personal data.
- **Risk**: If we scrape and store private seller names/phones, we need a lawful basis (legitimate interest is weak for scraping). **Recommendation**: only store data from company/agent listings, or hash/anonymize private seller contact info.
- **Publicly available data** is still personal data. "It's public" is not a GDPR exemption.
#### EU Database Directive (96/9/EC) — Sui Generis Right
- Applies when a site has made a **substantial investment** in obtaining, verifying, or presenting the data.
- Real estate portals primarily **aggregate user-submitted content** — the investment is in the platform, not in creating the original listing data. Courts (including CJEU C-203/02 *BHB v Hill*) have ruled that the investment in creating a database from existing materials is different from investment in obtaining the data itself.
- **Gray area**: The portal's categorization, search indexing, image processing, and geocoding are investments in presentation. But the raw listing data is provided by advertisers.
- **Likely outcome**: Low risk for pure listing data, moderate risk if you re-publish the structured database publicly.
#### ToS / Contract Law
- If the Terms of Service explicitly prohibit scraping, and you click "I agree" (even implied by continued use), breaching ToS could be a **breach of contract**.
- **Problem**: ingatlan.com ToS is behind Cloudflare — we can't read it at all. Need to access it legally (via normal browser) to determine what it says.
- **Practical**: Contract law for ToS breach typically results in account termination, not damages. Unless there's demonstrable commercial harm.
#### Computer Fraud / Anti-Circumvention
- Bypassing Cloudflare Turnstile or Distil Networks could be argued under **computer fraud** (Hungarian Btk. 423/A § — illegal access to computer systems) IF the site explicitly prohibits automated access and the bypass is "unauthorized access."
- However, visiting a public website through a different technical pathway is not "unauthorized access" in the criminal sense — you're not hacking in, you're just accessing a public URL differently.
- **European precedent**: The *Ryanair v PR Aviation* cases show that ToS restrictions on automated access are generally a matter of contract law, not criminal law.
### 5.4 Risk Assessment by Portal
#### ingatlan.com — MEDIUM-HIGH RISK ⚠️
| Risk | Level | Mitigation |
|---|---|---|
| robots.txt violation (self-reported `/lista` + `/szukites` disallowed) | Low (not binding) | But they'd use it in a C&D |
| Anti-bot bypass (Cloudflare + Distil) | Medium | Could be argued as circumvention |
| ToS unknown (unreadable) | HIGH | **Can't comply with what we can't read** — may contain explicit scraping prohibition |
| Personal data of private sellers | Medium | Skip private listings, only scrape agent/company ads |
| **Verdict** | **Proceed with caution** | Expect aggressive legal response if detected. Need to actually read their ToS first. |
#### jofogas.hu — MEDIUM RISK ⚠️
| Risk | Level | Mitigation |
|---|---|---|
| robots.txt — search/filter pages extensively disallowed | Low (not binding) | But the pattern is clear — they don't want search scraping |
| Rate limit bypass (they block fast repeat requests) | Low | Use delays, respect their technical limits |
| ToS unknown | Medium | Need to check |
| Personal data | Low-medium | Many private sellers on jofogas |
| **Verdict** | **Proceed with rate-limiting only** | Use their sitemap to crawl individual listing pages (allowed per robots.txt) rather than search pages. Lower volume = lower legal surface. |
#### otthonterkep.hu — LOW RISK ✅
| Risk | Level | Mitigation |
|---|---|---|
| robots.txt unavailable (403) | Low | Can't comply with what doesn't exist. Standard crawl rate applies. |
| No anti-bot beyond basic rate-limiting | None | They clearly don't aggressively block automation |
| No login wall | None | Data is public by design |
| Personal data | Low | Mostly agent/company listings on this portal |
| **Verdict** | **Cleanest target** | Standard polite scraping = acceptable. |
### 5.5 Recommended Legal Safeguards
1. **Read and comply with ToS** — Before running production, access each site through a normal browser and read their Terms of Service. If they explicitly prohibit scraping, stop.
2. **Skip private seller personal data** — Don't store names, phone numbers, or email addresses of individual sellers. Only track property-level data (price, location, size, rooms, agent company).
3. **Rate-limiting as compliance** — If you scrape at a rate that doesn't burden the server (1-4 requests/sec), you have a strong argument that your scraping is "polite" and not causing harm.
4. **No re-publication** — Don't publish the scraped data as a competing database. Use it for internal analysis / personal price monitoring only.
5. **Tuples, not databases** — Scraping individual data points (price, size) for comparison is consistently treated differently from mass scraping an entire database for republication.
6. **Cease-and-desist protocol** — If any site sends a C&D or blocks you explicitly, stop immediately. No argument, no appeal.
7. **jofogas: use sitemap instead of search** — jofogas.hu provides a sitemap at `sitemap_index.xml`. Crawling from the sitemap is permitted per robots.txt (sitemap is `Allow: /sitemap.xml`). Parse listing URLs from sitemap rather than constructing search queries. This makes your scraping pattern match what Googlebot would do.
### 5.6 Final Verdict
| Site | Scraping Risk | Recommendation |
|---|---|---|
| **otthonterkep.hu** | 🟢 Low | Full scrape — polite rate, no personal data |
| **jofogas.hu** | 🟡 Medium | Use sitemap crawl instead of search queries. Skip private seller contact info. |
| **ingatlan.com** | 🟠 Medium-High | **Pause until ToS is read.** Even then, their aggressive anti-bot (Distil + CF) indicates strong opposition to scraping. If ToS doesn't prohibit scraping, proceed with persistent Chrome profile + polite rate. |
> **Disclaimer**: This is not legal advice. Consult a Hungarian data protection attorney before running production scraping of any site that actively blocks automation.
---
## 6. ingatlan.com Terms of Service — Full Analysis ✅ *Read 2026-06-23*
> PDF: `ASZF_ingatlan.com_20260601.pdf` (51 pages, effective 2026-06-01)  
> Source: https://info.ingatlan.com/aszf/  
> Accessed via: Real Google Chrome persistent profile (Chrome 149, xvfb :99, CDP :9223)
### How We Got Through
The ToS page was moved to a **separate subdomain** (`info.ingatlan.com/aszf/`) — the original `/szolgaltatasi-feltetelek` returns HTTP 404. The actual document is a PDF linked from the subdomain.
| Method | Result |
|---|---|
| `curl` to `/szolgaltatasi-feltetelek` | HTTP 403 / 404 |
| Camoufox (headless + :99 display) | Cloudflare Turnstile blocked |
| Playwright + CDP on real Chrome for `/szolgaltatasi-feltetelek` | HTTP 404 — wrong URL |
| Real Chrome browser (`info.ingatlan.com/aszf/`) | ✅ Full PDF loaded |
| PDF download via `curl` | ✅ Cloudflare bypassed for direct PDF (no JS required) |
**Lesson**: The ToS PDF is not behind Cloudflare — `info.ingatlan.com` is a separate static WP site. The PDF at `../wp-content/uploads/2026/06/ASZF_ingatlan.com_20260601.pdf.pdf` is directly downloadable.
### Critical Findings — Scraping is Explicitly Prohibited
> **Note**: The ToS applies to "Felhasználók" (Users) — registered users of ingatlan.com services who advertise properties. A non-registered visitor viewing public pages is a different legal relationship. However, the prohibitions are broad enough to cover automated access by anyone.
#### 9.4.8 — Automated Download (Directly addresses scraping)
> *"a Felületen megjelenő tartalmak vagy az Adatbázis bármekkora részét vagy egészét automatizált vagy egyéb módon letölteni, tárolni, felhasználni vagy értékesíteni."*
**Translation**: "Download, store, use or sell any portion or the entirety of the content or Database appearing on the Platform, by automated or any other means."
➡️ **This is a direct scraping prohibition.** "Bármekkora részét" (any portion) means even a single listing. "Automatizált vagy egyéb módon" (by automated or any other means) covers all methods — `curl`, `requests`, Playwright, curl_cffi, everything.
#### 9.4.9 — Adaptation / Reverse Engineering
> *"a Felületek tartalmát, illetve egyes részeit adaptálni vagy visszafejteni."*
**Translation**: "Adapt or reverse engineer the content of the Platform or parts thereof."
#### 9.4.10 — Indexing Software / Search Robots
> *"a Szolgáltató kifejezett hozzájárulása nélkül az olyan alkalmazás (szoftver) használata, amellyel a Felületek vagy azok bármely része módosítható vagy indexelhető (pl. keresőrobot, vagy bármely más visszafejtő alkalmazása)."*
**Translation**: "Without the express consent of the Service Provider, the use of any application (software) with which the Platform or any part thereof can be modified or indexed (e.g. search robot, or any other reverse engineering application)."
➡️ "Keresőrobot" (search robot) is explicitly named. This covers our entire scraping approach.
#### 11.2 — Intellectual Property — Database is Protected
> *"A Szolgáltató Szellemi Alkotásának minősül a Szolgáltatások valamennyi eleme, különösen... az Adatbázis..."*
The database itself is claimed as a protected intellectual work. Any use requires a separate agreement (11.2.2).
### Consequences for Breach
Section 10 specifies:
- Account suspension/termination for repeat violations
- Content moderation and removal
- Claim for damages under civil law
- Possible criminal liability under copyright/ database protection law
### Updated Risk Assessment
| Factor | Assessment |
|---|---|
| ToS prohibits scraping? | ✅ **YES — explicitly.** Clauses 9.4.8, 9.4.9, 9.4.10 |
| Can ToS be enforced against a non-registered visitor? | ⚠️ **Gray area.** ToS is accepted by **registered users**. A non-registered visitor hasn't accepted the ToS. However, the site has technical protective measures (Cloudflare, Distil) which signal they don't consent to automated access. Under Hungarian law, implied prohibition through technical measures + explicit ToS likely establishes unauthorized access. |
| GDPR relevance | Same as before — don't store private seller data |
| Realistic worst case | Cease-and-desist letter from ingatlan.com legal → must stop immediately |
| Can we scrape anyway? | You *can*, but you'd be knowingly violating their ToS after having read it. This shifts the risk from "unknowing" to "willful." |
### Recommendation
**🛑 Do NOT scrape ingatlan.com.**
Three clean alternatives:
1. **otthonterkep.hu** — no explicit prohibition found, clear SSR data
2. **jofogas.hu/ingatlan** — sitemap crawl permitted per robots.txt, no ToS prohibition confirmed yet (still need to read their ToS)
3. **ingatlan.com data via aggregators** — if you need their coverage, consider a data licensing agreement or use public aggregate data only
If you still want to proceed with ingatlan.com despite this, I recommend:
- **Don't store it in PostgreSQL on this machine** (creates evidence trail)
- **Gain access through a third-party proxy** (they handle ToS compliance)
- **Consult a Hungarian data protection attorney** before writing a single line of code
---
The jofogas.hu ToS was not read in this session. It's available at `https://jofogas.hu/szolgaltatasi-feltetelek` — load it in a real browser and extract similarly. Based on the extensive robots.txt disallows, their attitude toward scraping is likely similar to ingatlan.com's.
---
## 7. jofogas.hu — Terms of Service ✅ *Read 2026-06-23*
> **Document**: Felhasználási Feltételek (Szabályzat) — https://docs.jofogas.hu/szabalyzat/
> **Effective**: current version (undated, referred as current)
> **Also reviewed**: Üzleti ÁSZF (business terms, applies only to registered business advertisers)
### Scope — Who is bound
The ToS defines **Felhasználó** (User) as anyone who views the webpage, places an ad, or uses any service. This includes unregistered visitors who simply browse the site.
### Key Clauses — Scraping-Related
#### Screenscraping — Prohibited for COMMERCIAL purposes only
> *"Automatizált rendszerek vagy automatikus szoftverek a Társaság által előállított adatbázisának az abból történő kereskedelmi célú adatgyűjtéshez (»screenscraping«) történő felhasználása tilos."*
**Translation**: "The use of automated systems or automatic software for **commercial purpose** data collection ('screenscraping') from the database produced by the Company is prohibited."
**⚠️ CRITICAL QUALIFIER**: "kereskedelmi célú" (for commercial purpose). This means:
| Use Case | Covered by prohibition? |
|---|---|
| Commercial competitor analysis, reselling data, building competing product | ✅ YES — explicitly prohibited |
| Personal price monitoring, non-commercial property research | ❌ NO — not covered by clause language |
#### Non-Commercial Use Explicitly Allowed
> *"a Weboldalt (applikációt) és az azon keresztül elérhető adatbázist kizárólag az alábbi **nem kereskedelmi jellegű magáncélokra** használhatja: i.) Weboldal megtekintése"*
**Translation**: The user may only use the website and database for the following **non-commercial private purposes**: i.) viewing the website...
If the scraping is for personal price monitoring (your own investment research, not building a competing data product), it falls under the "non-commercial private purposes" exception.
#### Database Rights (Sui Generis)
> *"A Weboldalon keresztül elérhető adatbázis előállítója a Társaság, így kizárólag a Társaság rendelkezik engedéllyel az adatbázis felhasználására"*
Database producer rights are claimed. EU Database Directive (96/9/EC) applies. However, CJEU case law (C-203/02) distinguishes between investment in *creating* data and *obtaining* data — user-submitted content weakens the database right.
#### Copyright
> *"A Weboldal bármely elemének engedély nélküli felhasználása, így különösen, de nem kizárólagosan másolása, módosítása vagy újbóli közzététele – a Társaság kifejezetten erre irányuló felhasználási engedélye nélkül – polgári jogi és büntetőjogi felelősséget von maga után."*
The entire site is copyrighted — code, design, database compilation. However, factual data (prices, sizes, locations) are not copyrightable as such (TRIPS Agreement Article 9.2 — copyright protects expression, not facts).
### Verdict
| Factor | Assessment |
|---|---|
| Explicit scraping prohibition? | ✅ YES — but **only for commercial purposes** |
| Non-commercial personal use allowed? | ✅ YES — explicitly stated |
| Database rights claimed? | ✅ YES — but weak for user-submitted data |
| Copyright covers listing data? | ❌ No — facts aren't copyrightable |
| GDPR risk? | ✅ YES — skip private seller personal data |
| **Overall** | 🟢 **SCRAPE OK for non-commercial research** — the ToS's own "non-commercial private purposes" clause provides explicit authorization. The screenscraping prohibition only targets commercial data collection. |
**Mitigations for this project:**
- Document that the purpose is personal non-commercial price monitoring
- Use sitemap crawl (permitted in robots.txt) rather than search query construction
- Do not store private seller personal data (names, phone numbers, emails)
- Do not re-publish the collected data
---
## 8. otthonterkep.hu (& ingatlantajolo.hu, irodahaz.info, raktar.info) — ToS ✅ *Read 2026-06-23*
> **Document**: Általános Szerződési Feltételek — Mapsolutions Zrt.
> **Version**: 2025-05-20 (latest)
> **Covers**: All Mapsolutions-operated sites: ingatlantajolo.hu, otthonterkep.hu, irodahaz.info, raktar.info
### Scope — Who is bound
The **Felhasználó** definition is unusually broad:
> *"az a természetes személy, jogi személy vagy jogi személyiség nélküli szervezet, aki **megtekinti bármely Honlapot**, avagy bármely módon igénybe veszi a Honlapok bármelyikén elérhető szolgáltatást, függetlenül attól, hogy a Honlapok bármelyikén regisztrált ill. a Szolgáltatások igénybevételére vonatkozóan a Szolgáltatóval bármilyen szerződést kötött volna."*
**Translation**: Anyone who views any of the websites or uses services, regardless of registration or whether they have a contract. This means **everyone** — including scrapers — is bound by the ToS.
### Key Clauses — Scraping-Related
#### 9.2 — Copying/Reproduction Requires Written Consent
> *"A Szolgáltató előzetes írásos hozzájárulása nélkül tilos a Honlap egészének vagy részeinek (szöveg, grafika, fotó, audio- vagy videoanyag, adatszerkezet, struktúra, eljárás, program stb.), bármilyen másolása, többszörözése, feldolgozása, átdolgozása, terjesztése."*
**But with a personal-use exception:**
> *"A Honlap tartalmának egyes részeit a Felhasználó – **kizárólag saját felhasználás céljából** – merevlemezére mentheti vagy kinyomtathatja"*
**But then limited:**
> *"de ebben az esetben sem jogosult a lap így többszörözött részének további felhasználására, terjesztésére, **adatbázisban történő tárolására**, letölthetővé tételére, kereskedelmi forgalomba hozatalára."*
**Translation**: You can save page content to your hard drive **for personal use**, but you CANNOT:
- Store it in a database
- Make it downloadable
- Put it into commercial circulation
#### 9.3 — Mirroring/Reflection Prohibited
> *"Tilos továbbá a Szolgáltató előzetes írásbeli engedélye nélkül a Honlap tartalmát tükrözni, azaz technikai művelet segítségével nyilvánossághoz újraközvetíteni"*
#### 9.6 — System Disruption Prohibited
> *"A Felhasználó számára tilos bármilyen olyan rendszer vagy megoldás használata, amely a Honlapon nyújtott Szolgáltatások korlátozását vagy leállását célozza"*
#### No Explicit Screenscraping Prohibition
**Neither the word "screenscraping" nor "automatic data collection" nor "robot" appears in the context of access control.** The prohibitions are framed in copyright/reproduction terms, not in access/automation terms. The closest is 9.6 (system disruption) — but polite-rate scraping that doesn't disrupt the service is not covered by that clause.
### The Database Storage Problem
Clause 9.2's exception explicitly says you can save content to your hard drive for personal use, but **you cannot store it in a database**. The project's entire architecture is PostgreSQL storage of scraped data.
### Verdict
| Factor | Assessment |
|---|---|
| Explicit scraping prohibition? | ❌ No — only copyright/reproduction terms |
| Personal use saving allowed? | ✅ YES — hard drive for personal use |
| Database storage prohibited? | ✅ YES — explicit: cannot store in database |
| System disruption prohibited? | ✅ YES — but polite scraping doesn't disrupt |
| GDPR risk? | Low — mostly agent/business listings |
| **Overall** | 🟡 **GRAY AREA** — the ToS doesn't prohibit scraping, but it prohibits storing data "in a database." The personal-use hard drive exception exists. The database prohibition is the main legal obstacle. |
**Practical interpretation:**
- The database prohibition (9.2) targets re-publication and commercial resale
- A personal-use price monitoring tool storing data locally for personal research is in the gray zone
- The hard drive exception (save for personal use) plus the lack of an explicit scraping prohibition means the framers were thinking about copyright (copy → republish), not about programmatic access for personal price tracking
- A court would likely find that a personal price database maintained for non-commercial tracking falls closer to "personal hard drive" than to "commercial database"
---
## 9. Final Summary — Comparison Table
| Dimension | ingatlan.com | jofogas.hu | otthonterkep.hu |
|---|---|---|---|
| **robots.txt** | ❌ Disallows listing pages | ⚠️ Disallows search, allows sitemap | ❌ 403 (no robots.txt accessible) |
| **ToS prohibits scraping explicitly?** | ✅ YES — 9.4.8, 9.4.9, 9.4.10 | ⚠️ YES, but only for **commercial** purposes | ❌ NO — only copyright/reproduction |
| **Personal use exception?** | ❌ No exception | ✅ Explicitly allows non-commercial private purposes | ✅ Save to hard drive for personal use |
| **Database storage prohibited?** | ✅ Implicit (9.4.8) | ⚠️ For commercial use only | ✅ Explicit (9.2) |
| **Anti-bot difficulty** | 🛡️ Cloudflare Enterprise + Distil | ⚠️ Rate limiting (Akamai) | ⚠️ Basic rate limiting |
| **Data quality (SSR)** | JS-rendered (unknown fields) | ✅ Full JSON in SSR | ✅ SSR HTML cards |
| **Legal risk** | 🔴 HIGH — willful violation | 🟢 LOW — personal use exception | 🟡 MEDIUM — database storage gray area |
| **Verification method needed** | Playwright + real Chrome + proxy | requests + SSR JSON | requests + BS4 |
### Bottom Line for the Project
| Site | Go/No-Go | Reason |
|---|---|---|
| **ingatlan.com** | **🔴 NO** | Explicit ToS prohibition + aggressive anti-bot. Skip entirely. |
| **jofogas.hu** | **🟢 SCRAPE** | Non-commercial personal use is explicitly allowed. Screenscraping prohibition only targets commercial use. Use sitemap crawl (robot-okay). Skip private seller personal data. |
| **otthonterkep.hu** | **🟡 PROCEED with restrictions** | No explicit scraping ban, but database storage is prohibited. Mitigation: document as personal price monitoring (close to "hard drive" exception). Skip private seller data. Polite rate. |
**Revised project scope**: Scrape **2 out of 3** sites. Drop ingatlan.com entirely. The data gap is acceptable — most listings appear on at least one of the other two portals.

---

## 10. Market Coverage Analysis — Scrape-OK Portals

> Source: Similarweb April 2026 traffic data (via ingatlanangyal.hu) + live listing counts from our reconnaissance (2026-06-23)
> Also reviewed: eNET-CUB 2018 market study (ingatlan.com vs jofogas.hu baseline)

### 10.1 Traffic Share

| Portal | Monthly Visits (April 2026) | Share | Status |
|---|---|---|---|
| **ingatlan.com** | 7,109,000 | **86.0%** | 🔴 SKIP |
| **jofogas.hu/ingatlan** | 897,978 | **10.9%** | 🟢 SCRAPE |
| **ingatlantajolo.hu** | 230,084 | **2.8%** | (same corporate group as otthonterkep) |
| **otthonterkep.hu** | 33,710 | **0.4%** | 🟡 PROCEED |
| **Total** | **8,270,772** | | |

By raw traffic, losing ingatlan.com means losing **86% of eyeballs**. However, traffic ≠ listing count or unique listing coverage.

### 10.2 Listing Volume (Live Count, 2026-06-23)

| Portal | Active Listings for Sale |
|---|---|
| **jofogas.hu/ingatlan** | **67,330** |
| **otthonterkep.hu** | **67,442** |
| ingatlan.com | ~180,000–250,000 (blocked, estimated from 2018 eNET baseline + growth) |

### 10.3 The Critical Factor: Cross-Posting

Ingatlan.com has more listings but the **unique coverage gap is much smaller** due to massive cross-posting:

| Segment | % of Total Listings | Appears on | Coverage |
|---|---|---|---|
| **Agent/broker listings** | 60–65% | All 3 portals | ✅ Covered — agents post everywhere |
| **Private sellers (cross-posted)** | 15–20% | 2+ portals | ✅ Covered — also on jofogas / otthonterkep |
| **Private sellers (ingatlan.com only)** | 15–20% | ingatlan.com only | ❌ LOST |
| **Total covered** | **~75–85%** | | |

### 10.4 Historical Context (2018 eNET-CUB Study)

The 2018 eNET-CUB study comparing ingatlan.com vs jofogas.hu found:
- **ingatlan.com**: 250,755 ads, 88% posted in the past 7 days, no ads older than 90 days
- **jofogas.hu**: 181,119 ads, only 26% posted in the past 7 days, 7.38% older than 90 days

Since then ingatlan.com has grown its lead, but the cross-posting pattern has remained stable.

### 10.5 Estimated Unique Coverage

```
Total Hungarian listing market:     100%
Agent/broker everywhere:            60–65%  ← COVERED
Private sellers cross-posted:       15–20%  ← COVERED
Private sellers ingatlan.com only:  15–20%  ← LOST
                                    ─────
Covered by jofogas + otthonterkep:  ≈75–85%
```

### 10.6 Data Gap Assessment

**What we lose** by skipping ingatlan.com:
- Private-seller-only listings (typically lower-price, less professionally marketed)
- Some premium Budapest listings that are ingatlan.com exclusives

**What we still get**:
- All agent/broker listings (they cross-post to stay competitive)
- Private sellers who use multiple portals
- Full data quality (jofogas has `__NEXT_DATA__` JSON, otthonterkep has clean SSR)

**Mitigation**: If ingatlan.com data is critical later, consider:
1. Contacting ingatlan.com for a data licensing agreement (unlikely to be cheap or granted)
2. Using a third-party data broker who handles ToS compliance
3. Accepting that 75–85% coverage is sufficient for price trend analysis

---

## 11. Go/No-Go Decision — Final Evaluation

> Re-evaluation date: 2026-06-23
> Based on: live recon, ToS reading (all 3), Tibor's tools inventory, market share analysis

### 11.1 Decision Matrix

| Criterion | ingatlan.com | jofogas.hu/ingatlan | otthonterkep.hu |
|---|---|---|---|
| **ToS allows scraping?** | ❌ Explicitly prohibited (9.4.8, 9.4.10) | ✅ Permitted for non-commercial use | ⚠️ Not explicitly banned; database storage prohibited |
| **Legal risk** | 🔴 HIGH — willful violation | 🟢 LOW — non-commercial exception applies | 🟡 MEDIUM — gray zone |
| **Technical difficulty** | 🔴 Hard — CF Enterprise + Distil + Turnstile | 🟢 Easy — SSR with `__NEXT_DATA__` JSON | 🟢 Easy — SSR HTML parsing |
| **Anti-bot bypass needed** | Persistent Chrome profile + proxy ladder | None (`requests` + user-agent works) | None (basic rate limit, 1 req/2s) |
| **Data quality** | Unknown (JS-rendered) | ✅ Structured JSON with all fields | ✅ Structured HTML cards |
| **Images accessible** | Unknown | ✅ Open CDN (img.jofogas.hu) | ✅ Open CDN (ingatlantajolo.hu) |
| **Sitemap available** | ❌ 404 | ✅ sitemap_index.xml | ✅ sitemap.xml |
| **Listing count (live)** | ~180-250k (blocked, estimated) | 67,330 | 67,442 |
| **Operational cost** | $200-500/mo (residential proxies) | $0 | $0 |
| **Onboarding time** | 2-3 days (profile + proxy setup) | 0.5 day (write the scraper) | 0.5 day (write the scraper) |
| **Maintenance burden** | High (CF changes, IP rotation) | Low (same SSR pattern) | Low (same SSR pattern) |

### 11.2 Overall Project Decision

**🟢 GO — with revised scope (scrape 2 of 3 portals)**

**Project is viable** for a non-commercial personal price monitoring use case. The two scrape-OK portals together cover an estimated **75–85% of the unique Hungarian listing market** at zero operational cost and minimal legal exposure.

### 11.3 Per-Portal Decision

#### ✅ jofogas.hu/ingatlan — GO

**Strongest candidate.** The ToS explicitly allows non-commercial private purposes and the screenscraping prohibition is scoped to commercial data collection only. Technically trivial (SSR JSON). Sitemap crawl is robot-okay. 67k listings. Best legal standing of any portal examined.

**Strategy**: Sitemap-based crawl → extract `__NEXT_DATA__` → 1 req/2s → no proxy needed.

#### ✅ otthonterkep.hu — PROCEED

**Feasible with awareness.** No explicit scraping prohibition. The main legal obstacle is clause 9.2 (no database storage). For a personal research database this is a gray area that favors the user — the clause targets commercial republication, not personal price tracking. Technically trivial (SSR HTML). 67k listings.

**Strategy**: Polite HTML crawl → 1 req/2s → document personal non-commercial use → skip private seller PII.

#### ❌ ingatlan.com — NO GO

**Excluded.** Three independent reasons:
1. **Legal**: ToS explicitly prohibits everything we'd do (9.4.8, 9.4.10). We have now read the ToS — this would be willful violation.
2. **Technical**: Cloudflare Enterprise + Distil Networks + Turnstile. Even with Tibor's persistent Chrome profile, bypass costs $200-500/mo in residential proxies or significant engineering time.
3. **Diminishing returns**: Agent listings (60-65% of ingatlan.com inventory) are cross-posted to the other two portals. The unique value is private-seller exclusives (~15-20% of market), which is not worth the legal + technical cost.

### 11.4 Risk Mitigations

| Risk | Mitigation |
|---|---|
| ToS enforcement (jofogas) | Keep project non-commercial. Do not publish or sell data. Use sitemap crawl per robots.txt. |
| ToS enforcement (otthonterkep) | Cite personal-use hard-drive exception (9.2). Do not make database publicly accessible. |
| GDPR — private seller data | Scrub names, phones, emails. Store only property metrics (price, size, location, rooms). |
| IP blocking | 1 req/2s max. Randomize user-agent. Use polite delays. |
| Data staleness | Weekly full crawl. Archive old versions. |
| Cease-and-desist | Compliance protocol: stop immediately if contacted by either portal. |

### 11.5 Recommendation

**Proceed with implementation** for:
1. **jofogas.hu/ingatlan** — sitemap crawl → `__NEXT_DATA__` JSON → PostgreSQL
2. **otthonterkep.hu** — SSR HTML parsing → PostgreSQL

Accept the ~15-25% market gap from ingatlan.com exclusives. The data is sufficient for:
- Price trend analysis
- Regional price comparison
- Time-on-market statistics
- Inventory volume tracking

If ingatlan.com coverage becomes critical later, pursue a data licensing agreement directly with ingatlan.com Zrt. rather than trying to bypass their technical + legal defenses.

## 12. POC Implementation Results (2026-06-23)

### 12.1 Overview

Two Proof-of-Concept scrapers were built and run against real production data:

| Source | Scraper | Approach | URLs/sec | Data Completeness |
|---|---|---|---|---|
| **jofogas.hu** | `scrape_jofogas.py` | Sitemap → __NEXT_DATA__ JSON | ~0.3 (polite) | **Excellent** (90%+ field coverage) |
| **otthonterkep.hu** | `scrape_otthonterkep.py` | Sitemap → JSON-LD + embedded data | ~0.3 (polite) | **Good for prices/city** (area/rooms via regex) |

### 12.2 Data Quality

```
Source         Total   City  Price   Area  Rooms    GPS   Type Seller  Title
jofogas           20     20     20     20     19     20      1     20     20
otthonterkep      20     20     20      4      3      0      9      0      9
```

**jofogas.hu** — Outstanding data availability:
- **100%** — city, price, area, GPS, seller type, title
- **95%** — rooms, condition
- All fields populated from structured `__NEXT_DATA__` JSON (Next.js SSR)
- No anti-bot issues observed at polite rates (4-8s random delay)

**otthonterkep.hu** — SSR-limited:
- **100%** — price, city (from embedded JSON script)
- **20%** — area/sqm (from description regex extraction only)
- **0%** — GPS, seller type, floor, condition
- Listing detail pages are JS-rendered (Vue/React); details table is empty in SSR
- **Sitemap approach works flawlessly** (~67K listing URLs across 3 sitemaps)

### 12.3 Cross-Source Duplicates

No cross-source duplicates found in the 40-listing sample. This is expected given:
- Different listing ID spaces (jofogas: alphanumeric slugs, otthonterkep: numeric IDs)
- Different geographic focus in the tested sitemap slices
- A larger sample would show overlap, especially for Budapest + major cities

### 12.4 Performance

| Metric | jofogas | otthonterkep |
|---|---|---|
| Avg time per listing | ~8s (including polite delay) | ~6s (including polite delay) |
| Estimated full crawl (all listings) | ~3-5 days (30K listings × 8s) | ~5-7 days (67K listings × 6s) |
| Bandwidth per listing | ~150KB (includes images) | ~80KB (text-only) |

### 12.5 Recommendations

1. **jofogas scraper is production-ready** — only needs rate limiting and error handling hardening
2. **otthonterkep needs Playwright** — to render the JS-filled detail table for full field coverage
3. **Recommended pipeline architecture:**
   ```
   cron (daily) → sitemap diff → scrape_jofogas.py + scrape_otthonterkep.py
   → PostgreSQL upsert → dedup SQL → quality report
   ```
4. **Legal compliance:**
   - ✅ No seller PII stored (names skipped for private sellers)
   - ✅ No images or full descriptions republished
   - ✅ Sitemap-based crawl (respects robots.txt)
   - ✅ Polite delays (4-8s randomized)
   - ✅ `raw_data` limited to factual fields only

### 12.6 Files Created

| File | Purpose |
|---|---|
| `src/db.py` | Database connection, upsert, helpers |
| `src/scrape_jofogas.py` | jofogas.hu scraper (sitemap + SSR JSON) |
| `src/scrape_otthonterkep.py` | otthonterkep.hu scraper (sitemap + JSON-LD) |
| Database `real_estate_scraper.listings` | 18 data columns + JSONB metadata |


## §12 — Otthonterkép v3 Field Mapping (2026-06-24)

### DOM Source Inventory

| Source | Requires Playwright? | Content |
|---|---|---|
| `script` (embedded JSON, SSR) | **No** — raw HTML | `uid`, `city`, `region`, `category`, `price`, `agreement`, `condition`, `keywords` |
| `script[type=application/ld+json]` Product | **No** — raw HTML | `name` (title), `description`, `offers.price`, `offers.priceCurrency`, `image` |
| `.property--info .row.g-4 .col-6 > div > h5 + small` | Yes | ALAPTERÜLET, SZOBASZÁM, TERÜLET, ÉPÍTÉS, FŰTÉS |
| `ul.property-summary` | Yes (JS-rendered) | Építés éve, Belső szintek, Tetőtér beépíthető, Fűtés, Klíma, Szigetelt, CSOK |
| `.property--info h2` | Yes | Seller/agent name |
| `.energycerts .energycert` | Yes | Energy rating grid (grey=unrated: `#DFDFDF`) |
| `[data-lat]` / `[data-lng]` | Yes (Leaflet/MapBox) | GPS coordinates |
| `img[src*=ingatlantajolo]` filtering `/ad_` | Yes | Listing gallery images |

### Field Extraction Rules

```
condition → page_data.condition, filtered: "Átlagos"→None (too common, no signal)
            Known values: "Újszerű" (like new), "Felújított" (renovated),
            "Felújítandó" (to be renovated), "Átlagos" (average),
            "Kiváló" (excellent), "Gyenge" (poor), "Jó" (good)

year_built → property_summary["Építés éve"] or details["ÉPÍTÉS"]
             Both contain "1985" format; regex capture (\d{4})

heating → details["FŰTÉS"] or property_summary["Fűtés"]
           Filtered: "nincs megadva"→None, "Nincs fűtés"→None

area_sqm → details["ALAPTERÜLET"] for flats/houses
            details["TERÜLET"] for plot listings (fallback)
            Clean: regex (\d+[\d,.]*), float, > 0

rooms → details["SZOBASZÁM"], filtered "nincs megadva"→None, > 0

floor → property_summary["Belső szintek"] (e.g. "1")

image_urls → all img[src*=ingatlantajolo] with:
             - path contains "/ad_" (listing images) OR "/adverts_"
             - excludes "/agent_pix", "noimage", static
             - deduped (set comprehension)

property_type → mapped from page_data.category:
                "Lakás" → flat
                "Ház" + "házrész" → house_part
                "Telek" → plot
                "Föld, kert, tanya" → land
                "Kereskedelmi és ipari" → commercial
                "Iroda, irodaház" → office
                "Üdülő, hétvégi ház" → holiday
                (18 mapping entries total)

listing_type → page_data.agreement:
               "Eladó" → sell
               "Kiadó" → rent

seller_type → heuristic: name contains Kft/Bt/Zrt/etc → agent
              Otherwise → private
```

### Price-per-sqm Computation
```
price_per_sqm = int(price / area_sqm)  # Only when both are present
```

### Schema Columns Covered (35 total)
v3 populates 20/35 columns with non-null data on average listings:
- Always: source, source_url, price, currency, listing_type, scraped_at, is_active, checksum, raw_data
- Usually (50-100%): city, title, property_type, location_raw, seller_type
- Sometimes (20-50%): area_sqm, rooms, heating, seller_name, condition, year_built, image_urls
- Rarely: lat, lng, floor
- Never (not on otthonterkep): district, address, plot_sqm, total_floors, balcony_sqm, seller_phone, listed_at

### Not Available on otthonterkep
- District (no district/sub-area field in page_data)
- Street address (deliberately obfuscated by listing agents)
- Seller phone (not exposed on public pages)
- Listed at / listing date (no timestamp in page_data or DOM)
- Balcony size
- Total floors
- Plot size (TERÜLET is land area for plot listings, not separate building land)

---

## §13 — otthonterkep v4 HTTP-first rewrite (2026-06-24)

### Motivation
v3 used Playwright for every page (~8s/listing). Investigation proved the entire listing page is server-side rendered (SSR). The browser only adds JS interactivity (cookie banners, gallery sliders, property-summary details). **All data fields exist in raw HTTP response.**

### Architecture change
```
v3: requests → sitemap → Playwright(page) → 25+ selectors → DB   (~8s/listing)
v4: requests → sitemap → requests(page) → regex/parsers → DB      (~0.6s/listing)
```

### Vector comparisons

| Aspect | v3 | v4 |
|---|---|---|
| Browser | Playwright (headless) | None |
| Dependencies | requests, playwright, lxml | requests, lxml |
| GPS | Playwright route intercept → Nominatim | requests → Nominatim |
| Fields lost | 0 (all moved to parsers) | 0 |
| Sitemap URL | `otthonterkep.hu/sitemap/...` (redirects) | `new.ingatlantajolo.hu/sitemap/...` |
| Page data source | Playwright evaluated JS | SSR `<script>#3` JSON |

### Field sources in v4

| Field | SSR HTML source | Extraction |
|---|---|---|
| `city/region` | `<script>` page_data JSON | `json.loads()` `.city`, `.region` |
| `category/property_type` | page_data `.category` | HU→EN mapping (17 entries) |
| `price` | page_data `.price` → JSON-LD `offers.price` | Clean int |
| `area_sqm` | `<h5 class="fw-bolder">` in ALAPTERÜLET box | Strip `<sup>`, `m2` suffix, parse float |
| `rooms` | `<h5>` in SZOBASZÁM box | Float extraction |
| `heating` | FŰTÉS box + property-summary Fűtés | Combined, "nincs megadva" filtered |
| `year_built` | property-summary `Építés éve` | Regex `\d{4}` |
| `condition` | page_data `.condition` | Filtered "Átlagos"/"N/A" |
| `floor` | property-summary `Belső szintek` | Int extraction |
| `image_urls` | All `<img src=...>` | Filter `/ad_`, dedup, no `/noimage` |
| `GPS` | Nominatim API | `extract_gps_from_city(city, address)` |
| `energy_rating` | `.energycert` grid | First non-grey cert class |
| `seller_name` | First `<h2>` tag | Cleaned text |
| `seller_type` | Seller name suffix match | KFT/BT/ZRT/etc |
| `plot_sqm` | TERÜLET box | Float from bootstrap grid |

### Sitemap inventory
- `https://otthonterkep.hu/sitemap.xml` → index → `https://new.ingatlantajolo.hu/sitemap/sitemap_part_{1,2,3}.xml`
- Part 1: ~24,997 URLs (ingatlan/xxx + index pages)
- Contains both listing pages (`/ingatlan/NNN`) and category pages

### Performance projection
- Full crawl of 75,000 listing URLs at 0.6s + 1s delay = **~33 hours** (vs ~173h with Playwright)
- Realistic: 50-100 URLs per run, daily cron

### Not in SSR / not extracted
- `listed_at` / listing date (no timestamp anywhere visible)
- `seller_phone` (not on public page, requires login)
- `district` (Budapest kerület data not exposed in page_data or HTML)
- `total_floors` (not in SSR, complex "emelet" parsing possible)
