.PHONY: run ingest install

install:
	pip install -r requirements.txt

run:
	uvicorn app.main:app --reload --port 8000

ingest:
	python -m app.ingestion.run

test:
	pytest tests/ -v
