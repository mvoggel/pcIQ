# pcIQ

Private credit distribution intelligence for BDC wholesalers.

Surfaces which RIAs are actively allocating to private credit **right now** — from SEC EDGAR public filings — so distribution teams know who to call before competitors do.

## Architecture

```
EDGAR (Form D + ADV) → Python ingestion → PostgreSQL → FastAPI → Next.js dashboard
```

**Three layers:**
1. **Data Foundation** — daily EDGAR pull, Form D/ADV parsing, entity resolution, Postgres
2. **Signal Engine** — RIA allocation scoring, competitor raise tracking, territory heat map
3. **Distribution Interface** — wholesaler daily digest, MD of Sales dashboard

## Stack

| Layer | Tech |
|-------|------|
| Ingestion | Python 3.11 + httpx |
| Validation | Pydantic v2 |
| Database | PostgreSQL via Supabase |
| Backend API | FastAPI |
| Frontend | Next.js (React) |
| Deployment | Vercel + Supabase cloud |
| Auth | Supabase Auth + row-level security |
| AI | Claude API (signal summarization) |

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env values, then:
make run
```

### Run EDGAR ingestion manually

```bash
cd backend
make ingest
```

## Phase 1 Focus (0–90 days)

- [x] Project scaffold
- [ ] EDGAR Form D fetcher + parser
- [ ] Entity resolution
- [ ] Form ADV / RIA enrichment
- [ ] Territory mapping + allocation scoring
- [ ] Basic Next.js dashboard
- [ ] Demo to CION MD of Sales
