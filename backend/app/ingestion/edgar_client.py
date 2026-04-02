"""
EDGAR API client for fetching Form D and Form ADV filings.

SEC EDGAR public APIs used:
  - Full-text search:  https://efts.sec.gov/LATEST/search-index
  - Filing index:      https://www.sec.gov/cgi-bin/browse-edgar
  - Submissions:       https://data.sec.gov/submissions/{CIK}.json
  - Filing document:   https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/primary_doc.xml

SEC policy: include a descriptive User-Agent header with company name and contact email.
Rate limit: max 10 requests/second. We stay well under that.
"""

import asyncio
from datetime import date, timedelta

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

EDGAR_BASE = "https://www.sec.gov"
EFTS_BASE = "https://efts.sec.gov"

# SEC asks for a max of 10 req/s; we use a conservative delay
_REQUEST_DELAY = 0.15  # seconds between requests


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_REQUEST_DELAY)
    return resp.json()


async def search_form_d_filings(
    start_date: date,
    end_date: date,
    *,
    max_results: int = 100,
) -> list[dict]:
    """
    Search EDGAR for Form D filings in a date range.

    Returns a list of filing metadata dicts, each containing:
        entity_name, cik, accession_no, filed_at, form_type
    """
    url = f"{EFTS_BASE}/LATEST/search-index"
    results = []
    from_offset = 0
    page_size = min(max_results, 100)

    async with httpx.AsyncClient() as client:
        while len(results) < max_results:
            params = {
                "q": "",
                "forms": "D",
                "dateRange": "custom",
                "startdt": start_date.isoformat(),
                "enddt": end_date.isoformat(),
                "from": from_offset,
                "hits.hits.total.value": "true",
            }
            data = await _get(client, url, params)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                src = hit.get("_source", {})
                # ciks is a list of 10-digit strings; take the first
                ciks = src.get("ciks", [])
                cik = ciks[0] if ciks else ""
                # _id looks like "edgar/data/1234567/0001234567-26-000001.txt"
                file_id = hit.get("_id", "")
                results.append(
                    {
                        "entity_name": src.get("entity_name", ""),
                        "cik": cik,
                        "file_id": file_id,
                        "filed_at": src.get("file_date", ""),
                        "form_type": src.get("form_type", "D"),
                        "period_of_report": src.get("period_of_report", ""),
                    }
                )

            total = data.get("hits", {}).get("total", {}).get("value", 0)
            from_offset += page_size
            if from_offset >= total or from_offset >= max_results:
                break

    return results[:max_results]


async def fetch_filing_index(cik: str, accession_no: str) -> dict:
    """
    Fetch the filing index for a given CIK + accession number.
    Returns the JSON index with document list.

    accession_no format: 0001234567-26-000001 (with dashes) or 0001234567-26-000001 (without)
    """
    # Normalize accession number: remove dashes for URL path
    acc_path = accession_no.replace("-", "")
    url = f"{EDGAR_BASE}/Archives/edgar/data/{cik.lstrip('0')}/{acc_path}/{accession_no}-index.json"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()


async def fetch_form_d_xml(cik: str, accession_no: str, timeout: float = 5.0) -> str:
    """
    Fetch the raw Form D XML document for a given filing.

    Returns the XML string for parsing by form_d_parser.
    timeout: seconds to wait — default 5s for modal path (cached path bypasses this).
    """
    acc_path = accession_no.replace("-", "")
    # Form D primary document is always primary_doc.xml
    url = f"{EDGAR_BASE}/Archives/edgar/data/{cik.lstrip('0')}/{acc_path}/primary_doc.xml"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=_headers(), timeout=timeout)
        resp.raise_for_status()
        await asyncio.sleep(_REQUEST_DELAY)
        return resp.text


async def fetch_filings_for_date_range(
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """
    Convenience wrapper: fetch all Form D filings for the past N days.
    Defaults to yesterday's filings.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=1)

    return await search_form_d_filings(start_date, end_date)
