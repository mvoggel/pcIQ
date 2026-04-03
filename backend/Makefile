PYTHON := python3
PIP := $(PYTHON) -m pip
MAX ?= 200

.PHONY: run ingest install test venv ingest-adv-state ingest-adv-crd ingest-adv-all enrich-rias ingest-feeders ingest-platform-rias platform-stats

venv:
	$(PYTHON) -m venv .venv
	@echo "Run: source .venv/bin/activate"

install:
	$(PIP) install -r requirements.txt

run:
	uvicorn app.main:app --reload --port 8000

ingest:
	$(PYTHON) -m app.ingestion.run

ingest-dry:
	$(PYTHON) -m app.ingestion.run --dry-run

# ADV / RIA ingestion — works from local (IAPD search endpoint, no auth needed)
#   make ingest-adv-crd CRD=173333          (single firm — e.g. iCapital)
#   make ingest-adv-state STATE=NY          (200 RIAs, override: make ingest-adv-state STATE=NY MAX=500)
#   make ingest-adv-all                     (all priority states, 200 each ≈ 2000 RIAs)
ingest-adv-crd:
	$(PYTHON) -m app.ingestion.run_adv --crd $(CRD)

ingest-adv-state:
	$(PYTHON) -m app.ingestion.run_adv --state $(STATE) --max $(MAX)

ingest-adv-all:
	@echo "Ingesting RIAs for all priority states (max=$(MAX) each)..."
	$(PYTHON) -m app.ingestion.run_adv --state NY --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state CA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state TX --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state FL --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state MA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state CT --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state NJ --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state IL --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state PA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state CO --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state WA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state GA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state NC --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state VA --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state OH --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state AZ --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state MN --max $(MAX)
	$(PYTHON) -m app.ingestion.run_adv --state MO --max $(MAX)
	@echo "Done. Run 'make enrich-rias' to backfill AUM from Railway."

# ── AUM backfill ─────────────────────────────────────────────────────────────

# RECOMMENDED: bulk enrichment via ADV PDF — runs locally, no Railway IP needed.
# Uses the public SEC ADV PDF URL (works from any IP, no auth).
# Enriches all null-AUM RIAs concurrently. Safe to interrupt and re-run.
# Expect ~60–90 min for 2,000 RIAs (state-registered firms skip fast).
#   make enrich-bulk              # all null-AUM RIAs
#   make enrich-bulk MAX=50       # test run — first 50
enrich-bulk:
	$(PYTHON) -m app.ingestion.bulk_enrich $(if $(MAX),--max $(MAX),)

# Railway trigger (legacy) — use enrich-bulk instead for faster results.
# Only useful if ADV PDF route is failing and you need IAPD detail endpoint.
# Requires INGEST_SECRET env var. Only 10 RIAs per call.
enrich-rias:
	@test -n "$(INGEST_SECRET)" || (echo "ERROR: set INGEST_SECRET env var first" && exit 1)
	curl -s -X POST https://pciq-production.up.railway.app/api/rias/enrich \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool
	@echo "\nCheck progress:"
	curl -s https://pciq-production.up.railway.app/api/rias/stats \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool

# ── ADV brochure platform scanner ────────────────────────────────────────────
# Scans Form ADV Part 2 brochures for platform mentions (iCapital, CAIS, etc.)
# Writes matches to ria_platforms with source='adv_brochure'.
# Pass 1 (EDGAR EFTS): fast, ~2–5 min. Pass 2 (direct brochure fetch): ~30–60 min.
#   make scan-brochures             # full scan (both passes)
#   make scan-brochures PASS=1      # EDGAR search only (quick test)
#   make scan-brochures PASS=2      # direct fetch only
#   make scan-brochures DRY=1       # dry run — print matches, no DB writes
scan-brochures:
	$(PYTHON) -m app.ingestion.brochure_scanner \
	  $(if $(filter 1,$(PASS)),--pass1-only,) \
	  $(if $(filter 2,$(PASS)),--pass2-only,) \
	  $(if $(DRY),--dry-run,) \
	  $(if $(V),--verbose,)

# ── Platform intelligence pipeline ───────────────────────────────────────────
# Step 1: scrape EDGAR for iCapital/CAIS/etc. access vehicle Form D filings
#   make ingest-feeders               # last 180 days (default)
#   make ingest-feeders DAYS=365      # last year
ingest-feeders:
	$(PYTHON) -m app.ingestion.run_feeder --days $(or $(DAYS),180)

ingest-feeders-dry:
	$(PYTHON) -m app.ingestion.run_feeder --days $(or $(DAYS),180) --dry-run

# Step 2: populate ria_platforms from a data source
#   make ingest-platform-rias              # EDGAR inference (default — run step 1 first)
#   make ingest-platform-rias SOURCE=cais  # scrape CAIS advisor directory
#   make ingest-platform-rias SOURCE=csv   # load from data/platform_rias.csv
ingest-platform-rias:
	$(PYTHON) -m app.ingestion.platform_scraper --source $(or $(SOURCE),edgar)

# Step 3: check counts (or trigger via Railway)
#   make platform-stats
platform-stats:
	@test -n "$(INGEST_SECRET)" || (echo "ERROR: set INGEST_SECRET env var first" && exit 1)
	curl -s https://pciq-production.up.railway.app/api/platforms/stats \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool

# Trigger full pipeline on Railway (feeder ingest → ria_platforms → stats)
platform-pipeline:
	@test -n "$(INGEST_SECRET)" || (echo "ERROR: set INGEST_SECRET env var first" && exit 1)
	@echo "Step 1: Ingesting feeder funds from EDGAR (last 180 days)..."
	curl -s -X POST "https://pciq-production.up.railway.app/api/platforms/ingest/feeder?days=180" \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool
	@echo "\nWaiting 90s for feeder ingest to complete..."
	@sleep 90
	@echo "\nStep 2: Populating ria_platforms via EDGAR inference..."
	curl -s -X POST "https://pciq-production.up.railway.app/api/platforms/ingest/rias?source=edgar" \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool
	@echo "\nWaiting 30s..."
	@sleep 30
	@echo "\nStats:"
	curl -s "https://pciq-production.up.railway.app/api/platforms/stats" \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool


# Signal reports — territory intelligence
signals:
	$(PYTHON) -m app.signals.run_signals --days 7

signals-northeast:
	$(PYTHON) -m app.signals.run_signals --days 7 --territory Northeast

test:
	pytest tests/ -v
