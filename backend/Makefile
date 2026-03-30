PYTHON := python3
PIP := $(PYTHON) -m pip

.PHONY: run ingest install test venv

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

# ADV / RIA ingestion — examples:
#   make ingest-adv-crd CRD=173333        (iCapital)
#   make ingest-adv-state STATE=NY
ingest-adv-crd:
	$(PYTHON) -m app.ingestion.run_adv --crd $(CRD)

ingest-adv-state:
	$(PYTHON) -m app.ingestion.run_adv --state $(STATE) --max 50

test:
	pytest tests/ -v
