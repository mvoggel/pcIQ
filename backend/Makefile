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

test:
	pytest tests/ -v
