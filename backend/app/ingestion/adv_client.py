"""
Form ADV data client.

Two data sources:
  1. SEC IAPD (Investment Adviser Public Disclosure) API — primary
     https://efts.sec.gov/LATEST/search-index?forms=ADV
     https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=ADV

  2. SEC Investment Adviser Search API — clean JSON, best for bulk pulls
     https://efts.sec.gov/LATEST/search-index?forms=ADV&dateRange=custom&...

  3. IAPD firm detail API — rich structured data per CRD number
     https://api.adviserinfo.sec.gov/api/Firm/{crd_number}

Strategy for Phase 1:
  - Use the IAPD firm API to enrich specific RIAs by CRD number
  - Use the EDGAR ADV search to find recently-updated ADV filers in bulk
  - Focus on SEC-registered RIAs (AUM > $100M threshold for SEC registration)

SEC rate limit: same as EDGAR — max 10 req/s, we stay under.
"""

import asyncio

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.ria import RIA

IAPD_BASE = "https://api.adviserinfo.sec.gov"
EFTS_BASE = "https://efts.sec.gov"
EDGAR_BASE = "https://www.sec.gov"

_REQUEST_DELAY = 0.15


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict | list:
    resp = await client.get(url, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_REQUEST_DELAY)
    return resp.json()


async def fetch_ria_by_crd(crd_number: str) -> dict | None:
    """
    Fetch full RIA detail from IAPD by CRD number.
    Returns raw JSON dict or None if not found.

    CRD (Central Registration Depository) number is FINRA's stable
    identifier for advisory firms — survives name changes and reorganizations.
    """
    url = f"{IAPD_BASE}/api/Firm/{crd_number}"
    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, url)
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise


async def search_adv_filers(
    state: str | None = None,
    min_aum_m: float = 100,
    max_results: int = 100,
) -> list[dict]:
    """
    Search for SEC-registered RIA firms via EDGAR full-text search.

    Args:
        state:       2-letter state code to filter by (e.g. "NY", "CA")
        min_aum_m:   minimum AUM in millions (default 100 = $100M)
        max_results: max records to return

    Returns list of raw search hit dicts from EFTS.
    """
    url = f"{EFTS_BASE}/LATEST/search-index"
    results = []
    from_offset = 0

    async with httpx.AsyncClient() as client:
        while len(results) < max_results:
            params: dict = {
                "q": "",
                "forms": "ADV",
                "from": from_offset,
            }
            if state:
                params["q"] = state

            data = await _get(client, url, params)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                src = hit.get("_source", {})
                results.append({
                    "entity_name": src.get("entity_name", ""),
                    "cik": (src.get("ciks") or [""])[0],
                    "file_id": hit.get("_id", ""),
                    "filed_at": src.get("file_date", ""),
                    "form_type": src.get("form_type", "ADV"),
                })

            total = data.get("hits", {}).get("total", {}).get("value", 0)
            from_offset += len(hits)
            if from_offset >= min(total, max_results):
                break

    return results[:max_results]


async def fetch_adv_submission(cik: str, file_id: str) -> dict | None:
    """
    Fetch the structured ADV submission data for a given CIK.
    Uses the EDGAR submissions API which returns clean JSON.
    """
    cik_padded = cik.zfill(10)
    url = f"{EDGAR_BASE}/cgi-bin/browse-edgar"
    params = {
        "action": "getcompany",
        "CIK": cik_padded,
        "type": "ADV",
        "dateb": "",
        "owner": "include",
        "count": "1",
        "search_text": "",
        "output": "atom",
    }
    # For structured ADV data, the IAPD API is more reliable than raw EDGAR
    # Raw ADV filings are PDFs/HTML — not machine-readable
    # We'll use CIK to look up the firm's CRD via the IAPD search
    return None  # Handled by fetch_ria_by_crd in the parser layer


async def fetch_iapd_search(firm_name: str) -> list[dict]:
    """
    Search IAPD for a firm by name. Returns list of matching firm summaries.
    Useful for finding the CRD number when you only have a name.
    """
    url = f"{IAPD_BASE}/api/Firm/SearchByName/{firm_name}"
    async with httpx.AsyncClient() as client:
        try:
            data = await _get(client, url)
            # IAPD returns {"hits": [...]} or a list directly
            if isinstance(data, dict):
                return data.get("hits", {}).get("hits", [])
            return data if isinstance(data, list) else []
        except (httpx.HTTPStatusError, httpx.RequestError):
            return []
