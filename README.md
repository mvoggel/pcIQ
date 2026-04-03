# pcIQ — Private Credit Distribution Intelligence

> Surface competitor fund raises and likely allocators for private credit distribution teams — powered by live SEC EDGAR data.

**Live app:** https://pc-iq.vercel.app (Clerk email OTP auth required)
**Backend:** https://pciq-production.up.railway.app
**Stack:** Python · FastAPI · PostgreSQL (Supabase) · Next.js 16 · React 19 · Tailwind v4 · Vercel · Railway

---

## What It Does

pcIQ monitors SEC Form D filings daily to answer the question every private credit wholesaler wakes up asking: *which competitor funds are being distributed in my territory right now, and which advisors are positioned to buy them?*

**For a wholesaler, a morning with pcIQ looks like this:**
- Open the signals feed → see competitor funds filed in the last 30 days, scored by territory relevance
- Click a fund → see which platforms (iCapital, CAIS, Lazard) are distributing it, the manager's AUM, and which RIA firms are likely or confirmed allocators
- Click an RIA → land on their IAPD profile in one click

**No vendor currently does this specifically for private credit distribution teams.** FINTRX sells contact databases. Dakota focuses on institutional LPs. Preqin covers fund benchmarking. None of them surface real-time competitor distribution activity by territory.

---

## Current Data State

| Table | Rows | Notes |
|-------|------|-------|
| `form_d_filings` | 180 days | ~100+ private credit signals per 30-day window |
| `rias` | ~3,600 | 18 states ingested. AUM enrichment ongoing via `make enrich-bulk` |
| `ria_platforms` | 756 | Enriched RIAs × 6 platforms — EDGAR inference (source-tagged per row) |
| `feeder_funds` | 137 | iCapital/CAIS access vehicles from EDGAR |
| `adv_enrichment` | ~126 | ADV PDF cache keyed by CRD, 30-day TTL |
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
make ingest-adv-all                     # All 18 states: NY CA TX FL MA CT NJ IL PA CO WA GA NC VA OH AZ MN MO

# AUM enrichment
make enrich-bulk              # RECOMMENDED: local bulk enrichment via ADV PDF (~60–90 min for 2,000 RIAs)
make enrich-bulk MAX=50       # Test run — first 50 RIAs only
make enrich-rias              # Legacy: Railway trigger (10 RIAs/call, requires INGEST_SECRET)

# Platform data
make ingest-feeders                    # Scan EDGAR for new iCapital/CAIS access vehicles
make ingest-platform-rias SOURCE=csv   # Load confirmed platform RIAs from data/platform_rias.csv
make ingest-platform-rias              # EDGAR inference fallback
make platform-stats                    # Show ria_platforms coverage summary
```

---

## Architecture

```
Browser (Next.js 16, React 19, Tailwind v4)
  ├── /signals    → Territory signal feed (scored Form D filings)
  ├── /cion       → CION fund NAV tracker + competitor registered funds
  └── Fund modal  → 4-source enrichment on click
        ├── Supabase DB row (instant)
        ├── Form D XML parse (~200ms)
        ├── EDGAR submissions API (~150ms)
        ├── IAPD + ADV PDF parse (~4–8s, cached after first load)
        ├── Confirmed Platform Allocators (platform partner + in territory + confidence badge)
        └── Likely Allocators (RIAs in fund territory, $100M+ AUM)

Backend (FastAPI + Python, Railway)
  ├── /api/signals              — territory scoring from Supabase
  ├── /api/fund/{cik}/{acc}     — 4-source parallel enrichment
  ├── /api/rias/enrich          — AUM backfill trigger (Railway IP, 10/call)
  ├── /api/rias/stats           — enrichment progress
  ├── /api/platforms/ingest/*   — feeder fund + RIA platform ingestion
  └── /api/cion/funds           — yfinance NAV data

Data Layer (Supabase / PostgreSQL)
  ├── form_d_filings         — core filing data
  ├── fund_platforms         — broker-dealer / platform recipients per filing
  ├── entities               — resolved issuer entities
  ├── territories            — state → territory mapping
  ├── rias                   — RIA firms (CRD, name, city, state, AUM)
  ├── adv_enrichment         — ADV PDF cache (keyed by CRD, 30-day TTL)
  ├── ria_platforms          — RIA ↔ platform relationships (source: csv | scrape | edgar_inferred)
  ├── feeder_funds           — iCapital/CAIS access vehicles from EDGAR
  └── ria_fund_allocations   — (schema-ready, empty) audit trail for Phase 2
```

---

## Signal Scoring Logic

Each Form D filing is scored 0–10 for territory relevance:

| Signal | Weight | Logic |
|--------|--------|-------|
| Known distribution platform (iCapital, CAIS, etc.) | +3 | Fund uses a recognized institutional platform |
| Territory state overlap | +2 | Solicitation states match configured territory |
| Offering size | +1 to +3 | Scaled by raise amount — institutional-size raises score highest |
| Filing freshness | +1 | Filed within last 7 days |
| Fund type | +1 | Private Equity Fund / Other Investment Fund / Hedge Fund |
| Micro raise penalty (<$2M) | -1 | Down-ranks noise |

---

## RIA Intelligence — How Allocators Work

Every fund modal shows two RIA sections:

**Confirmed Platform Allocators** — RIAs with a known relationship to the platforms distributing this fund. Three-signal inference: (1) RIA is in the right geography, (2) RIA appears in `ria_platforms` for a matching platform, (3) platform appears in the fund's `salesCompensationList`. Each RIA shows a source confidence badge:
- **✓ confirmed** (green) — sourced from real platform directory CSV
- **EDGAR inferred** (grey) — derived from feeder fund cross-reference

**Likely Allocators** — RIAs in the fund's solicitation territory. Pulled from the `rias` table filtered by territory state overlap. Sorted by AUM where available.

> **Coverage note:** Run `make enrich-bulk` once to achieve 70–80%+ AUM coverage in ~60–90 min. The weekly GitHub Action then maintains enrichment for newly ingested RIAs. The IAPD detail endpoint is 403 from local IPs — the bulk script uses the public ADV PDF URL which works from anywhere.

---

## Automation (GitHub Actions)

Three scheduled workflows — all use the `INGEST_SECRET` repository secret:

| Workflow | Schedule | What it does |
|----------|----------|-------------|
| `daily-ingest.yml` | Daily 8am ET | Pulls last 2 days of Form D filings via `/api/ingest/trigger` |
| `weekly-ria-enrich.yml` | Sunday 4am ET | Calls `/api/rias/enrich` 4× with gaps → 40 RIAs/week |
| `weekly-feeder-scan.yml` | Monday 5am ET | Scans EDGAR for new access vehicles via `/api/platforms/ingest/feeder` |

**Required:** Set `INGEST_SECRET` in repo → Settings → Secrets and variables → Actions.

**To pause auto-scheduling:** remove the `schedule:` block from the workflow file. The `workflow_dispatch:` block stays, so you can still trigger manually from the Actions tab.

---

## Known Constraints

| Constraint | Detail |
|-----------|--------|
| IAPD detail endpoint | `/firms/registration/summary/{crd}` returns 403 from local/residential IPs. Works from Railway. Use `make enrich-bulk` for local enrichment — it hits the ADV PDF URL which has no IP restriction. |
| IAPD search params | `state=` works. `iapd_state_cd=` is silently ignored. `query` cannot be empty. |
| supabase-py ordering | `nullsfirst=False` is correct. `nulls_last=True` throws a TypeError — was causing Railway OOM restart loops. |
| Railway memory | Starter plan = 512MB. PDFs >8MB are skipped. **Upgrade to Hobby ($20/mo) before any CION demo.** |
| Platform RIA coverage | 756 `ria_platforms` rows = EDGAR inference (source-tagged). Import real directory CSV to upgrade to confirmed. Template at `backend/data/platform_rias_template.csv`. |
| `private_fund_aum` | Column exists, value is 0. ADV parser reads Part 1A only. Schedule D parse needed for private fund AUM breakdown. |

---

## Data Sources

| Source | What It Provides | Access |
|--------|-----------------|--------|
| SEC EDGAR (Form D) | Private fund raises, distribution platforms, solicitation states | Public API, no auth |
| EDGAR submissions API | Fund website, phone, SIC code | Public, `data.sec.gov` |
| IAPD search API | RIA firm CRD, name, location, relying adviser count | Public, `adviserinfo.sec.gov` |
| ADV PDF | Manager AUM, employees, client type breakdown (Item 5) | Public URL — works from any IP |
| yfinance | NAV, price history, moving averages for registered funds | Public |
| Platform CSV (iCapital/CAIS) | Confirmed RIA roster per platform | Manual export — see `backend/data/platform_rias_template.csv` |

---

## Deployment

### Frontend (Vercel)
Auto-deploys on every push to `main`.

### Backend (Railway)
Auto-deploys on every push to `main`. Environment variables managed in Railway dashboard.

> **Before any CION demo:** Upgrade Railway from Starter (512MB) to Hobby ($20/mo, 8GB RAM). One large ADV PDF on Starter can still trigger an OOM crash.

---

## Roadmap

**Now — coverage depth:**
- `make enrich-bulk` — bulk AUM enrichment to 70–80%+ in one session
- Import platform directory CSV to upgrade EDGAR inference → confirmed
- `private_fund_aum` backfill via Schedule D parser

**Phase 2 — commercial build:**
- Salesforce data push (one-click CRM export)
- Wholesaler daily email digest (top 5 signals per territory)
- Multi-tenant territory configuration
- `ria_fund_allocations` audit trail population

**Phase 3 — scale:**
- AI narrative layer (Claude API): plain-English weekly digest
- Cross-firm competitive intelligence synthesis
- Data partnership conversations (Altigo, Broadridge wallet share)

---

## Reference Customer

**CION Investments** — publicly traded BDC (~$2B AUM). MD of Sales has validated the product direction.
Key quote: *"Who is buying what products is a gold mine."*

---

*Product spec: `pcIQ_ProductSpec_V4_3.docx`*
