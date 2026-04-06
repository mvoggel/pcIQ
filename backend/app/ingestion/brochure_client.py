"""
IAPD Part 2A brochure client.

Fetches the ADV Part 2A narrative brochure for a given CRD number.

WHY THIS NEEDS TO RUN FROM RAILWAY
───────────────────────────────────
The IAPD brochure API endpoints block local/residential IPs with HTTP 403:
  - https://api.adviserinfo.sec.gov/firms/brochures/IA/{crd}  → 403 locally
  - https://api.adviserinfo.sec.gov/firms/registration/summary/{crd} → 403 locally
Railway's shared IP range passes these blocks — same reason fetch_ria_by_crd()
is called from Railway in rias.py rather than from local scripts.

HOW IT WORKS
─────────────
1. GET /firms/brochures/IA/{crd}   → list of brochures with version IDs
2. Pick the most recent Part 2A entry
3. GET https://files.adviserinfo.sec.gov/IAPD/Content/Common/crd_iapd_Brochure.aspx
       ?BRCHR_VRSN_ID={version_id}   → Part 2A PDF bytes
4. Extract text (all pages — Part 2A brochures are 10–60 pages of narrative prose)
5. Return plain text for platform keyword scanning

This module is imported by rias.py (Railway) — not called from local scripts directly.
"""

from __future__ import annotations

import asyncio
import io
import re

import httpx
import pdfplumber

IAPD_API_BASE   = "https://api.adviserinfo.sec.gov"
IAPD_FILES_BASE = "https://files.adviserinfo.sec.gov"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.adviserinfo.sec.gov/",
    "Origin": "https://www.adviserinfo.sec.gov",
}

_BROCHURE_ENDPOINTS = [
    "{base}/firms/brochures/IA/{crd}",
    "{base}/firms/brochures/{crd}",
    "{base}/firms/registration/brochures/{crd}",
]

_PART2A_LABELS = {"part 2a", "brochure", "adv part 2", "part2a"}
_MAX_PDF_BYTES  = 20 * 1024 * 1024   # 20 MB ceiling
_REQUEST_TIMEOUT = 25                # seconds


def _is_part2a(brochure: dict) -> bool:
    """Heuristic: is this brochure entry a Part 2A filing?"""
    label = (
        brochure.get("brchureType")
        or brochure.get("type")
        or brochure.get("filing_type")
        or ""
    ).lower()
    return any(term in label for term in _PART2A_LABELS)


def _extract_version_id(brochure: dict) -> str | None:
    """Pull the version ID from whatever field IAPD uses."""
    for key in ("brchureVrsn", "brchr_vrsn_id", "versionId", "id", "brochureVersionId"):
        val = brochure.get(key)
        if val:
            return str(val).strip()
    return None


def _extract_filing_date(brochure: dict) -> str:
    """Return an ISO-ish date string for sorting (empty = oldest)."""
    for key in ("filingDate", "filing_date", "date", "filedDate"):
        val = brochure.get(key) or ""
        if val:
            return str(val)
    return ""


def _parse_brochure_list(data) -> list[dict]:
    """
    IAPD brochure endpoints return data in several possible shapes.
    Normalize to a flat list of brochure dicts.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Common shapes:
        #   {"brochureList": [...]}
        #   {"brochures": [...]}
        #   {"hits": {"hits": [...]}}
        for key in ("brochureList", "brochures", "Brochures", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return val
        hits = data.get("hits", {})
        if isinstance(hits, dict):
            inner = hits.get("hits", [])
            if isinstance(inner, list):
                return [h.get("_source", h) for h in inner]
    return []


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF (runs in thread — blocking I/O)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


async def fetch_part2a_text(crd: str, client: httpx.AsyncClient) -> tuple[str, str]:
    """
    Download and parse the Part 2A brochure for a given CRD.

    Returns (text, status) where:
      text   = extracted plain text (empty string on any failure)
      status = one of: "ok", "no_brochures", "no_part2a", "fetch_error",
               "pdf_too_large", "403", "404", "timeout"
    """
    # Step 1 — get brochure list from IAPD
    brochure_list: list[dict] = []
    for template in _BROCHURE_ENDPOINTS:
        url = template.format(base=IAPD_API_BASE, crd=crd)
        try:
            resp = await client.get(url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
            if resp.status_code == 403:
                return "", "403"
            if resp.status_code == 404:
                return "", "404"
            if resp.status_code != 200:
                continue
            brochure_list = _parse_brochure_list(resp.json())
            if brochure_list:
                break
        except httpx.TimeoutException:
            return "", "timeout"
        except Exception:
            continue

    if not brochure_list:
        return "", "no_brochures"

    # Step 2 — find most recent Part 2A
    part2a = [b for b in brochure_list if _is_part2a(b)]

    # Fallback: if no typed Part 2A, try all brochures (some firms label them differently)
    candidates = part2a or brochure_list

    # Sort descending by date — newest first
    candidates.sort(key=_extract_filing_date, reverse=True)

    version_id = None
    for candidate in candidates:
        vid = _extract_version_id(candidate)
        if vid:
            version_id = vid
            break

    if not version_id:
        return "", "no_part2a"

    # Step 3 — download the brochure PDF
    pdf_url = (
        f"{IAPD_FILES_BASE}/IAPD/Content/Common/crd_iapd_Brochure.aspx"
        f"?BRCHR_VRSN_ID={version_id}"
    )
    try:
        resp = await client.get(pdf_url, headers=_HEADERS, timeout=_REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return "", f"pdf_{resp.status_code}"

        pdf_bytes = resp.content
        if len(pdf_bytes) < 1_000:
            return "", "pdf_too_small"
        if len(pdf_bytes) > _MAX_PDF_BYTES:
            return "", "pdf_too_large"

        # Verify it's actually a PDF (not an HTML error page)
        if not pdf_bytes[:4] == b"%PDF":
            return "", "not_a_pdf"

    except httpx.TimeoutException:
        return "", "timeout"
    except Exception as exc:
        return "", f"error:{type(exc).__name__}"

    # Step 4 — extract text (CPU-bound → thread)
    try:
        text = await asyncio.to_thread(_extract_text_from_pdf, pdf_bytes)
        return text, "ok"
    except Exception:
        return "", "parse_error"
