PYTHON := python3
PIP := $(PYTHON) -m pip
MAX ?= 200

.PHONY: run ingest install test venv ingest-adv-state ingest-adv-crd ingest-adv-all enrich-rias

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
	@echo "Done. Run 'make enrich-rias' to backfill AUM from Railway."

# AUM backfill — must be triggered against Railway (IAPD detail is 403 from local IPs)
# Requires INGEST_SECRET env var to be set.
# Run multiple times until enrich count reaches 0.
enrich-rias:
	@test -n "$(INGEST_SECRET)" || (echo "ERROR: set INGEST_SECRET env var first" && exit 1)
	curl -s -X POST https://pciq-production.up.railway.app/api/rias/enrich \
	  -H "Authorization: Bearer $(INGEST_SECRET)" \
	  -G --data-urlencode "batch=100" | python3 -m json.tool
	@echo "\nCheck progress:"
	curl -s https://pciq-production.up.railway.app/api/rias/stats \
	  -H "Authorization: Bearer $(INGEST_SECRET)" | python3 -m json.tool

# Signal reports — territory intelligence
signals:
	$(PYTHON) -m app.signals.run_signals --days 7

signals-northeast:
	$(PYTHON) -m app.signals.run_signals --days 7 --territory Northeast

test:
	pytest tests/ -v
