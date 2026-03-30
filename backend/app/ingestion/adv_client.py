"""
Form ADV data client.

Data sources (in priority order):
  1. IAPD API — rich structured data per CRD, requires browser-like headers
     https://api.adviserinfo.sec.gov/firms/registration/summary/{crd}

  2. EDGAR submissions API — reliable, works with SEC User-Agent, filing metadata
     https://data.sec.gov/submissions/CIK{cik_padded}.json

  3. EDGAR EFTS full-text search — for bulk ADV filer discovery
     https://efts.sec.gov/LATEST/search-index?forms=ADV

SEC rate limit: max 10 req/s. We stay well under.
"""

import asyncio

import httpx
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.config import settings

IAPD_BASE  = "https://api.adviserinfo.sec.gov"
DATA_BASE  = "https://data.sec.gov"
EFTS_BASE  = "https://efts.sec.gov"
EDGAR_BASE = "https://www.sec.gov"

_REQUEST_DELAY = 0.15

# IAPD blocks plain programmatic User-Agents — needs Referer from their own site
_IAPD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.adviserinfo.sec.gov/",
    "Origin": "https://www.adviserinfo.sec.gov",
}

# EDGAR APIs accept the SEC-required descriptive User-Agent
_EDGAR_HEADERS = {
    "User-Agent": settings.edgar_user_agent,
    "Accept": "application/json",
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_not_exception_type(httpx.HTTPStatusError),
)
async def _get(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    params: dict | None = None,
) -> dict | list:
    resp = await client.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_REQUEST_DELAY)
    return resp.json()


# ---------------------------------------------------------------------------
# IAPD — structured RIA detail by CRD
# ---------------------------------------------------------------------------

_IAPD_ENDPOINTS = [
    "{base}/firms/registration/summary/{crd}",
    "{base}/api/Firm/{crd}",
    "{base}/api/Firm/summary/{crd}",
]


async def fetch_ria_by_crd(crd_number: str) -> dict | None:
    """
    Fetch full RIA detail from IAPD by CRD number.
    Tries multiple endpoint formats — IAPD has changed their API paths.
    Returns raw JSON dict or None if not found / unavailable.
    """
    async with httpx.AsyncClient() as client:
        for template in _IAPD_ENDPOINTS:
            url = template.format(base=IAPD_BASE, crd=crd_number)
            try:
                data = await _get(client, url, headers=_IAPD_HEADERS)
                if data:
                    return data
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                # Try next endpoint on 403/other errors
                continue
            except Exception:
                continue
    return None


async def fetch_iapd_search(firm_name: str) -> list[dict]:
    """
    Search IAPD for a firm by name.
    Returns list of matching firm summaries (each has crdNumber).
    """
    urls = [
        f"{IAPD_BASE}/search/firm",
        f"{IAPD_BASE}/api/Firm/SearchByName/{firm_name}",
    ]
    params = {"query": firm_name, "hl": "true", "nrows": "10", "start": "0"}

    async with httpx.AsyncClient() as client:
        for url in urls:
            try:
                p = params if "search/firm" in url else None
                data = await _get(client, url, headers=_IAPD_HEADERS, params=p)
                # Different endpoints return different shapes
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    # {"hits": {"hits": [...]}} or {"firms": [...]}
                    hits = (
                        data.get("hits", {}).get("hits")
                        or data.get("firms")
                        or data.get("results")
                        or []
                    )
                    return hits
            except Exception:
                continue
    return []


# ---------------------------------------------------------------------------
# EDGAR submissions API — reliable fallback, no IAPD dependency
# ---------------------------------------------------------------------------

async def fetch_edgar_submissions(cik: str) -> dict | None:
    """
    Fetch all filing submissions for a CIK from data.sec.gov.
    Returns the submissions JSON (includes filing history + company facts).

    This is the most reliable SEC data source — no auth, no Referer needed.
    """
    if not cik:
        return None
    cik_padded = cik.zfill(10)
    url = f"{DATA_BASE}/submissions/CIK{cik_padded}.json"
    async with httpx.AsyncClient() as client:
        try:
            return await _get(client, url, headers=_EDGAR_HEADERS)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise


# ---------------------------------------------------------------------------
# EDGAR EFTS — bulk ADV filer discovery
# ---------------------------------------------------------------------------

async def search_adv_filers(
    state: str | None = None,
    max_results: int = 100,
) -> list[dict]:
    """
    Search EDGAR for ADV filers. Returns list of filing metadata dicts.

    Args:
        state:       2-letter state code to filter by (used as query term)
        max_results: max records to return
    """
    url = f"{EFTS_BASE}/LATEST/search-index"
    results: list[dict] = []
    from_offset = 0

    async with httpx.AsyncClient() as client:
        while len(results) < max_results:
            params: dict = {
                "q": state or "",
                "forms": "ADV",
                "from": from_offset,
            }
            data = await _get(client, url, headers=_EDGAR_HEADERS, params=params)
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
                })

            total = data.get("hits", {}).get("total", {}).get("value", 0)
            from_offset += len(hits)
            if from_offset >= min(total, max_results):
                break

    return results[:max_results]
