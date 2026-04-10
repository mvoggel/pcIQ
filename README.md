# pcIQ — Private Credit Distribution Intelligence

> Surface competitor fund raises and likely allocators for private credit distribution teams — powered by live SEC EDGAR data.

**Live app:** https://pc-iq.vercel.app (Clerk email OTP auth required)
**Backend:** https://pciq-production.up.railway.app
**Stack:** Python · FastAPI · PostgreSQL (Supabase) · Next.js 16 · React 19 · Tailwind v4 · Vercel · Railway

---

## What It Does

pcIQ monitors SEC Form D filings daily to answer the question every private credit wholesaler wakes up asking: *which competitor funds are being distributed in my territory right now, and which advisors are positioned to buy them?*

**Three intelligence layers:**

1. **Signals** — Competitor Form D filings scored by territory relevance. See what's raising in your market, who's distributing it, and how much has been sold.
2. **Funds** — Click any fund to see the manager's AUM, distribution platforms, confirmed and likely RIA allocators, and a live trail of recent advisor deployments into that fund.
3. **Advisors** — Ranked call list of RIAs scored across three SEC data sources. Every row shows why they rank — Form D allocations, 13F BDC holdings, and AUM tier. Click any row for a full call brief and one-click Salesforce sync.

**No vendor does this specifically for private credit distribution teams.** FINTRX sells contact databases. Dakota focuses on institutional LPs. Preqin covers fund benchmarking. None surface real-time competitor distribution activity by territory.

---

## Current Data State

| Table | Rows | Notes |
|-------|------|-------|
| `form_d_filings` | 180-day rolling | ~100+ private credit signals per 30-day window |
| `rias` | ~2,543 | 18 states ingested. 71% AUM enrichment (ceiling — remaining are state-registered) |
| `ria_platforms` | 756+ | EDGAR-inferred platform memberships, source-tagged per row |
| `ria_fund_allocations` | Live | Allocation events written during Form D ingest + backfill complete |
| `thirteenf_holdings` | 947 | 13F BDC holder universe — 558 filers, 365-day lookback |
| `feeder_funds` | 137 | iCapital/CAIS access vehicles from EDGAR |
| `adv_enrichment` | ~1,800 | ADV PDF cache keyed by CRD, 30-day TTL |
| `territories` | 5 | NE / SE / MW / SW / WC |

---

## Local Development

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Supabase project (free tier works)
- Railway account (for backend deployment)

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key

# EDGAR User-Agent (SEC policy requires contact info)
EDGAR_USER_AGENT="pcIQ yourname@email.com"

# Salesforce (optional — Contact button gracefully disabled if unset)
SALESFORCE_CLIENT_ID=...
SALESFORCE_CLIENT_SECRET=...
SALESFORCE_REFRESH_TOKEN=...
SALESFORCE_INSTANCE_URL=https://yourorg.salesforce.com
```

> **Railway env vars** (INGEST_SECRET, etc.) are managed in the Railway dashboard — not needed for local development.

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

---

## Available Commands

```bash
# Form D ingestion
make ingest              # Pull last 2 days of Form D filings → Supabase
make ingest-dry          # Test run — no DB writes

# RIA ingestion (18 states)
make ingest-adv-state STATE=NY          # Single state
make ingest-adv-state STATE=NY MAX=500  # Higher limit for dense states
make ingest-adv-all                     # All 18 states

# AUM enrichment (run locally — Railway 512MB limit)
make enrich-bulk              # Bulk enrichment via ADV PDF (~60–90 min for 2,000 RIAs)
make enrich-bulk MAX=50       # Test run — first 50 RIAs only

# 13F BDC holder universe (run locally — Railway memory limit)
python -m app.ingestion.run_thirteenf 365   # Full year lookback
python -m app.ingestion.run_thirteenf 90    # Last quarter only

# Platform data
make ingest-feeders                    # Scan EDGAR for new iCapital/CAIS access vehicles
make ingest-platform-rias SOURCE=csv   # Load confirmed platform RIAs from data/platform_rias.csv
make ingest-platform-rias              # EDGAR inference fallback
make platform-stats                    # Show ria_platforms coverage summary

# Backfill allocation events for historical filings
POST /api/ingest/backfill-allocations  # Populates ria_fund_allocations for all existing Form D rows
```

---

## Architecture

```
Browser (Next.js 16, React 19, Tailwind v4)
  ├── /signals    → Territory signal feed (scored Form D filings)
  ├── /advisors   → Ranked RIA call list with priority scoring and territory filter
  ├── /cion       → CION fund NAV tracker + competitor registered funds
  └── Modals
        ├── Fund modal  → 4-source enrichment + recent advisor deployment trail
        └── Advisor modal → Full call brief, Form D 90d funds, Salesforce contact sync

Backend (FastAPI + Python, Railway)
  ├── /api/signals                          — territory scoring from Supabase
  ├── /api/advisors                         — ranked RIA list with priority scores
  ├── /api/advisors/{crd}/funds             — Form D funds an advisor has deployed to (90d)
  ├── /api/fund/{cik}/{acc}                 — 4-source parallel fund enrichment
  ├── /api/fund/{cik}/{acc}/movements       — recent advisor deployments into a specific fund
  ├── /api/cion/funds                       — CION fund data
  ├── /api/cion/platform-stats              — live DB stats for the CION IQ bar
  ├── /api/salesforce/push-lead             — Salesforce OAuth lead push (Refresh Token flow)
  ├── /api/ingest/trigger                   — Form D ingestion trigger
  ├── /api/ingest/backfill-allocations      — retroactive ria_fund_allocations population
  ├── /api/rias/enrich                      — AUM backfill trigger (Railway)
  └── /api/platforms/ingest/*               — feeder fund + platform RIA ingestion

Data Layer (Supabase / PostgreSQL)
  ├── form_d_filings         — core filing data
  ├── fund_platforms         — broker-dealer / platform recipients per filing
  ├── entities               — resolved issuer entities
  ├── territories            — state → territory mapping
  ├── rias                   — RIA firms (CRD, name, city, state, AUM)
  ├── adv_enrichment         — ADV PDF cache (keyed by CRD, 30-day TTL)
  ├── ria_platforms          — RIA ↔ platform relationships (source: csv | scrape | edgar_inferred)
  ├── feeder_funds           — iCapital/CAIS access vehicles from EDGAR
  ├── ria_fund_allocations   — allocation events (ria_id × filing_id × signal_date) — live
  └── thirteenf_holdings     — 13F BDC holder universe (filer, CUSIP, value, ria_crd if matched)
```

---

## Advisor Priority Scoring

The `/advisors` page ranks RIAs using a three-tier system computed from public SEC data:

| Badge | Criteria |
|-------|----------|
| **High Priority** | Form D allocations + 13F BDC holdings + AUM ≥ $1B — all three confirmed |
| **Medium** | Any two of the three pillars above |
| **Watchlist** | One signal, or AUM ≥ $500M |

Scoring is computed server-side in `backend/app/api/advisors.py` and returned as `priority_score: 1 | 2 | 3` — the frontend renders badges directly from this value (no client-side re-calculation).

---

## Signal Scoring Logic

Each Form D filing is scored 0–10 for territory relevance:

| Signal | Weight | Logic |
|--------|--------|-------|
| Known distribution platform (iCapital, CAIS, etc.) | +3 | Fund uses a recognized institutional platform |
| Territory state overlap | +2 | Solicitation states match configured territory |
| Offering size | +1 to +3 | Scaled by raise amount |
| Filing freshness | +1 | Filed within last 7 days |
| Fund type | +1 | Private Equity Fund / Other Investment Fund / Hedge Fund |
| Micro raise penalty (<$2M) | -1 | Down-ranks noise |

---

## RIA Intelligence — How Allocators Work

Every fund modal shows:

**Recent Advisor Deployment** — pulled from `ria_fund_allocations`, showing which RIAs have deployment events linked to this exact fund filing, with dates and AUM. Sorted most-recent first.

**Confirmed Platform Allocators** — RIAs with a known relationship to the platforms distributing this fund. Three-signal inference: (1) geography match, (2) RIA appears in `ria_platforms` for a matching platform, (3) platform appears in the fund's `salesCompensationList`. Source confidence badge per row:
- **confirmed** (green) — sourced from real platform directory CSV
- **EDGAR inferred** (grey) — derived from feeder fund cross-reference

**Likely Allocators** — shown only when no confirmed data exists. RIAs in the fund's territory by AUM, sourced from Form ADV.

Platform name matching uses substring logic (brand name vs. legal name): `"iCapital"` matches `"iCapital Markets LLC"`, `"CAIS"` matches `"CAIS Capital LLC"`.

---

## 13F Ingestion

Tracks the institutional BDC holder universe — every filer who holds ARCC, MAIN, ORCC, BXSL, HTGC, GBDC, NMFC, TPVG, CSWC, or PFLT in their 13F-HR filing.

- **Rate limiting:** concurrency=3, delay=0.4s — stays under SEC's 10 req/s limit with no 429 errors
- **RIA matching:** CIK-based match (primary) + normalized name match (fallback) against the `rias` table
- **Match rate:** ~7/558 filers match to tracked RIAs — expected; most 13F filers are hedge funds, mutual funds, and family offices, not registered investment advisers
- **Run locally** (Railway 512MB limit): `python -m app.ingestion.run_thirteenf 365`

---

## Salesforce Integration

The Contact button in the advisor modal uses OAuth 2.0 Refresh Token flow:

1. Backend exchanges refresh token for access token via `https://login.salesforce.com/services/oauth2/token`
2. Creates a Lead record with firm name, CRD, AUM, priority label, and top signal bullets
3. Handles duplicates gracefully (returns `status: "duplicate"` instead of error)
4. Returns `status: "not_configured"` if Railway env vars are not set — button stays visible but silently skips

**Required Railway env vars:** `SALESFORCE_CLIENT_ID`, `SALESFORCE_CLIENT_SECRET`, `SALESFORCE_REFRESH_TOKEN`, `SALESFORCE_INSTANCE_URL`

---

## Automation (GitHub Actions)

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| `daily-ingest.yml` | Daily 8am ET | Pulls last 2 days of Form D filings + writes allocation events |
| `weekly-ria-enrich.yml` | Sunday 4am ET | Calls `/api/rias/enrich` 4× → 40 RIAs/week |
| `weekly-feeder-scan.yml` | Monday 5am ET | Scans EDGAR for new access vehicles |

**Required:** Set `INGEST_SECRET` in repo → Settings → Secrets and variables → Actions.

> **13F and bulk AUM enrichment run locally** — Railway's 512MB RAM limit causes OOM on these workloads. Run `python -m app.ingestion.run_thirteenf 365` and `make enrich-bulk` from your machine; both write directly to Supabase.

---

## Known Constraints

| Constraint | Detail |
|-----------|--------|
| Railway memory | Starter plan = 512MB. 13F and bulk enrichment must run locally. **Upgrade to Hobby ($20/mo) before any CION demo.** |
| IAPD detail endpoint | Returns 403 from local/residential IPs. Works from Railway. Use `make enrich-bulk` for local enrichment — hits ADV PDF URL which has no IP restriction. |
| RIA enrichment ceiling | 71% (1,812/2,543). Remaining ~731 are state-registered (under $110M AUM) — no IAPD/ADV PDF available. |
| Platform name matching | `ria_platforms` stores brand names ("iCapital"); `fund_platforms` stores legal names ("iCapital Markets LLC"). Matching uses substring containment, not exact equality. |
| `private_fund_aum` | Column exists, value is 0. ADV parser reads Part 1A only. Schedule D parse needed for private fund AUM breakdown. |
| Platform RIA coverage | All 756 `ria_platforms` rows are EDGAR-inferred. Import real directory CSV to upgrade to confirmed. Template at `backend/data/platform_rias_template.csv`. |

---

## Deployment

### Frontend (Vercel)
Auto-deploys on every push to `main`.

### Backend (Railway)
Auto-deploys on every push to `main`. Environment variables managed in Railway dashboard.

> **Before any CION demo:** Upgrade Railway from Starter (512MB) to Hobby ($20/mo, 8GB RAM). One large ADV PDF on Starter can trigger an OOM crash.

---

## Roadmap

**Now — signal quality:**
- Import platform directory CSV (iCapital/CAIS) to upgrade EDGAR inference → confirmed
- Activate Salesforce env vars on Railway
- `private_fund_aum` backfill via Schedule D parser

**Phase 2 — distribution:**
- Wholesaler daily email digest (top 5 signals per territory)
- Multi-tenant territory configuration
- Advisor list filters (AUM range, state, platform)

**Phase 3 — scale:**
- AI narrative layer (Claude API): plain-English weekly digest per territory
- Cross-firm competitive intelligence synthesis
- Data partnership conversations (Altigo, Broadridge wallet share)

---

## Reference Customer

**CION Investments** — publicly traded BDC (~$2B AUM). MD of Sales has validated the product direction.
Key quote: *"Who is buying what products is a gold mine."*

---

*Product spec: `pcIQ_AdvisorFirst_Strategy.docx`*
