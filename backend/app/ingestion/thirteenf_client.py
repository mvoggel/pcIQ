"""
EDGAR client for Form 13F-HR filings (institutional investment manager holdings).

13F-HR = quarterly holdings report for managers with >$100M in 13(f) securities.
We use it to find which firms hold BDC-type positions — a direct proxy for
CION's buyer universe.

EDGAR APIs used:
  - EFTS search:    https://efts.sec.gov/LATEST/search-index?forms=13F-HR
  - Filing index:   https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/-index.json
  - Holdings XML:   primary_doc.xml or infotable.xml within the filing

BDC CUSIPs tracked (add more as needed):
  ARCC  04010L103  Ares Capital
  MAIN  56035L104  Main Street Capital
  ORCC  09260D107  Blue Owl Capital Corp
  BXSL  09261G100  Blackstone Secured Lending
  HTGC  427096100  Hercules Capital
  GBDC  38173M102  Golub Capital BDC
  NMFC  64828T201  New Mountain Finance
  TPVG  87267L109  TriplePoint Venture Growth
  CSWC  22348Q102  Capital Southwest
  PFLT  69318G106  PennantPark Floating Rate
"""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

log = logging.getLogger(__name__)

EDGAR_BASE = "https://www.sec.gov"
EFTS_BASE  = "https://efts.sec.gov"
_DELAY     = 0.15   # stay well under SEC's 10 req/s limit

# BDC issuers we care about: CUSIP → ticker
BDC_CUSIPS: dict[str, str] = {
    "04010L103": "ARCC",
    "56035L104": "MAIN",
    "09260D107": "ORCC",
    "09261G100": "BXSL",
    "427096100": "HTGC",
    "38173M102": "GBDC",
    "64828T201": "NMFC",
    "87267L109": "TPVG",
    "22348Q102": "CSWC",
    "69318G106": "PFLT",
}

# Also match by partial name (some filers use variations)
BDC_NAME_FRAGMENTS = {
    "ARES CAPITAL", "MAIN STREET", "BLUE OWL CAPITAL CORP", "BLACKSTONE SECURED",
    "HERCULES CAPITAL", "GOLUB CAPITAL BDC", "NEW MOUNTAIN FINANCE",
    "TRIPLEPOINT", "CAPITAL SOUTHWEST", "PENNANTPARK",
}


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept":     "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    resp = await client.get(url, params=params, headers=_headers(), timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_DELAY)
    return resp.json()


_MAX_XML_BYTES = 20 * 1024 * 1024  # 20 MB — skip monster filings


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=2, max=8))
async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(
        url,
        headers={**_headers(), "Accept": "text/xml,application/xml,*/*"},
        timeout=20,
    )
    resp.raise_for_status()
    if len(resp.content) > _MAX_XML_BYTES:
        log.debug("Skipping oversized XML (%d bytes): %s", len(resp.content), url)
        raise ValueError(f"XML too large ({len(resp.content)} bytes)")
    await asyncio.sleep(_DELAY)
    return resp.text


def _parse_efts_hit(hit: dict) -> dict:
    """Extract filing metadata from a single EFTS hit dict."""
    src     = hit.get("_source", {})
    ciks    = src.get("ciks", [])
    cik     = ciks[0] if ciks else ""
    file_id = hit.get("_id", "")  # format: "{accession_no}:{filename}"

    acc_no   = ""
    doc_name = ""
    if ":" in file_id:
        parts    = file_id.split(":", 1)
        acc_no   = parts[0]
        doc_name = parts[1]
    elif "/" in file_id:
        fname = file_id.split("/")[-1]
        for ext in (".txt", ".htm", ".html", ".xml"):
            if fname.lower().endswith(ext):
                fname = fname[:-len(ext)]
                break
        if fname.count("-") == 2:
            acc_no = fname

    entity_name = src.get("entity_name", "")
    if not entity_name:
        display = src.get("display_names", [])
        if display and isinstance(display[0], dict):
            entity_name = display[0].get("name", "")
        elif display and isinstance(display[0], str):
            entity_name = display[0]

    return {
        "entity_name":      entity_name,
        "cik":              cik,
        "accession_no":     acc_no,
        "doc_name":         doc_name,
        "filed_at":         src.get("file_date", ""),
        "period_of_report": src.get("period_of_report", ""),
        "_raw_id":          file_id,
    }


async def search_13f_by_cusips(
    start_date: date,
    end_date: date,
    *,
    max_per_cusip: int = 200,
) -> list[dict]:
    """
    Search EDGAR for 13F-HR filings that mention our tracked BDC CUSIPs.

    Searching by CUSIP means EFTS returns the exact infotable file (not the
    cover sheet), so doc_name is correct and we skip the index-lookup step.

    Returns deduplicated list of filing dicts, one per unique accession number.
    """
    url  = f"{EFTS_BASE}/LATEST/search-index"
    seen: dict[str, dict] = {}   # accession_no → filing dict

    async with httpx.AsyncClient() as client:
        for cusip in BDC_CUSIPS:
            from_offset = 0
            page_size   = 100
            fetched     = 0

            while fetched < max_per_cusip:
                params = {
                    "q":         f'"{cusip}"',
                    "forms":     "13F-HR",
                    "dateRange": "custom",
                    "startdt":   start_date.isoformat(),
                    "enddt":     end_date.isoformat(),
                    "from":      from_offset,
                }
                try:
                    data = await _get(client, url, params)
                except Exception as exc:
                    log.warning("EFTS search failed for CUSIP %s: %s", cusip, exc)
                    break

                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    break

                for hit in hits:
                    filing = _parse_efts_hit(hit)
                    acc    = filing["accession_no"]
                    if acc and acc not in seen:
                        seen[acc] = filing

                total       = data.get("hits", {}).get("total", {}).get("value", 0)
                fetched    += len(hits)
                from_offset += page_size
                if from_offset >= min(total, max_per_cusip):
                    break

            log.info("CUSIP %s: found %d total filings", cusip, fetched)

    results = list(seen.values())
    log.info("Total unique 13F filers holding tracked BDCs: %d", len(results))
    return results


# Common infotable filenames used by 13F filers — tried if index lookup fails
_FALLBACK_XML_NAMES = [
    "form13fInfoTable.xml",
    "informationtable.xml",
    "infotable.xml",
    "13fInfoTable.xml",
    "primary_doc.xml",
]


async def _fetch_filing_index(
    client: httpx.AsyncClient, cik_str: str, acc_path: str, accession_no: str
) -> list[str]:
    """
    Fetch the filing index JSON and return XML filenames sorted: infotable first.
    Falls back to common known filenames if the index is unavailable.
    """
    index_url = f"{EDGAR_BASE}/Archives/edgar/data/{cik_str}/{acc_path}/{accession_no}-index.json"
    try:
        data = await _get(client, index_url)
        items = data.get("directory", {}).get("item", [])
        if not items:
            log.debug("Empty index for %s/%s — using fallback names", cik_str, accession_no)
            return _FALLBACK_XML_NAMES
        xml_files = [
            item["name"] for item in items
            if isinstance(item, dict) and item.get("name", "").lower().endswith(".xml")
        ]
        xml_files.sort(key=lambda n: (
            0 if "infotable" in n.lower() else
            1 if "13f" in n.lower() else
            2
        ))
        log.debug("Index for %s: %s", accession_no, xml_files)
        return xml_files or _FALLBACK_XML_NAMES
    except Exception as exc:
        log.debug("Index fetch failed for %s/%s: %s — using fallback names", cik_str, accession_no, exc)
        return _FALLBACK_XML_NAMES


async def fetch_13f_holdings(cik: str, accession_no: str, doc_name: str = "") -> list[dict]:
    """
    Fetch and parse the infotable XML for a 13F-HR filing.

    doc_name: filename extracted from EFTS _id (e.g. "primary_doc.xml") — tried first.
    Falls back to filing index lookup, then common hardcoded filenames.

    Returns list of dicts: {issuer_name, cusip, ticker, value_usd, shares, investment_discretion}
    value_usd is in whole dollars (13F reports in thousands — multiplied by 1000).
    """
    acc_path = accession_no.replace("-", "")
    # EDGAR stores filings under the CIK embedded in the accession number
    # (the submitter/filer CIK), NOT the entity CIK from the EFTS result.
    # e.g. accession "0001420506-26-000184" → path CIK "1420506"
    path_cik = accession_no.split("-")[0].lstrip("0") or cik.lstrip("0")
    base     = f"{EDGAR_BASE}/Archives/edgar/data/{path_cik}/{acc_path}"

    async with httpx.AsyncClient() as client:
        # When doc_name comes from a CUSIP search, EFTS gives us the exact
        # infotable filename — try it first without any index round-trip.
        # Only fall back to index + hardcoded names if that fails.
        candidates: list[str] = []
        if doc_name:
            candidates.append(doc_name)
        for n in _FALLBACK_XML_NAMES:
            if n not in candidates:
                candidates.append(n)

        for fname in candidates:
            try:
                xml_text = await _get_text(client, f"{base}/{fname}")
            except Exception:
                continue
            holdings = _parse_infotable(xml_text)
            if holdings is not None:
                return holdings

        # Last resort: index lookup (costs an extra HTTP round-trip)
        index_names = await _fetch_filing_index(client, path_cik, acc_path, accession_no)
        for fname in index_names:
            if fname in candidates:
                continue
            try:
                xml_text = await _get_text(client, f"{base}/{fname}")
            except Exception:
                continue
            holdings = _parse_infotable(xml_text)
            if holdings is not None:
                return holdings

    return []


def _parse_infotable(xml_text: str) -> list[dict] | None:
    """
    Parse 13F infotable XML and return only BDC-related holdings.

    Returns None  → wrong file (no infoTable elements found, or parse error) — try next candidate.
    Returns []    → right file, but this filer holds none of our tracked BDCs.
    Returns [...]  → BDC holdings found.

    This distinction matters: primary_doc.xml is the cover sheet and has zero
    infoTable elements — we must keep trying other files rather than stopping.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Check whether this file contains any infoTable elements at all.
    # If not, it's the wrong document — tell the caller to try the next one.
    has_infotable = any(_tag(el) == "infoTable" for el in root.iter())
    if not has_infotable:
        return None

    # Strip namespace prefix if present (e.g. {http://...}infoTable → infoTable)
    def _tag(el: ET.Element) -> str:
        tag = el.tag
        return tag.split("}")[-1] if "}" in tag else tag

    holdings: list[dict] = []
    for entry in root.iter():
        if _tag(entry) != "infoTable":
            continue

        issuer  = ""
        cusip   = ""
        value   = 0
        shares  = 0
        discr   = ""
        for child in entry:
            t = _tag(child)
            if   t == "nameOfIssuer":          issuer = (child.text or "").strip().upper()
            elif t == "cusip":                 cusip  = (child.text or "").strip()
            elif t == "value":                 value  = int(child.text or 0)
            elif t == "investmentDiscretion":  discr  = (child.text or "").strip()
            elif t == "shrsOrPrnAmt":
                for sub in child:
                    if _tag(sub) == "sshPrnamt":
                        shares = int(sub.text or 0)

        # Match by CUSIP (preferred) or by name fragment
        ticker = BDC_CUSIPS.get(cusip)
        if not ticker:
            if not any(frag in issuer for frag in BDC_NAME_FRAGMENTS):
                continue
            ticker = issuer  # use name as fallback ticker label

        holdings.append({
            "issuer_name":           issuer,
            "cusip":                 cusip,
            "ticker":                ticker,
            "value_usd":             value * 1000,   # 13F reports in thousands
            "shares":                shares,
            "investment_discretion": discr,
        })

    return holdings
