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


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    resp = await client.get(url, headers={**_headers(), "Accept": "text/xml,application/xml,*/*"}, timeout=30)
    resp.raise_for_status()
    await asyncio.sleep(_DELAY)
    return resp.text


async def search_13f_filings(
    start_date: date,
    end_date: date,
    *,
    max_results: int = 500,
) -> list[dict]:
    """
    Search EDGAR for 13F-HR filings in a date range.

    Returns list of dicts: {entity_name, cik, accession_no, filed_at, period_of_report}
    """
    url = f"{EFTS_BASE}/LATEST/search-index"
    results: list[dict] = []
    from_offset = 0
    page_size = 100

    async with httpx.AsyncClient() as client:
        while len(results) < max_results:
            params = {
                "forms":     "13F-HR",
                "dateRange": "custom",
                "startdt":   start_date.isoformat(),
                "enddt":     end_date.isoformat(),
                "from":      from_offset,
            }
            data = await _get(client, url, params)
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for hit in hits:
                src     = hit.get("_source", {})
                ciks    = src.get("ciks", [])
                cik     = ciks[0] if ciks else ""
                file_id = hit.get("_id", "")  # format: "{accession_no}:{filename}"

                # 13F EFTS _id format: "0001234567-26-000001:primary_doc.xml"
                acc_no   = ""
                doc_name = ""
                if ":" in file_id:
                    parts    = file_id.split(":", 1)
                    acc_no   = parts[0]   # "0001234567-26-000001"
                    doc_name = parts[1]   # "primary_doc.xml"
                elif "/" in file_id:
                    # Fallback: old path-style _id (Form D style)
                    fname = file_id.split("/")[-1]
                    for ext in (".txt", ".htm", ".html", ".xml"):
                        if fname.lower().endswith(ext):
                            fname = fname[:-len(ext)]
                            break
                    if fname.count("-") == 2:
                        acc_no = fname

                # 13F filings use display_names, not entity_name
                entity_name = src.get("entity_name", "")
                if not entity_name:
                    display = src.get("display_names", [])
                    if display and isinstance(display[0], dict):
                        entity_name = display[0].get("name", "")
                    elif display and isinstance(display[0], str):
                        entity_name = display[0]

                results.append({
                    "entity_name":      entity_name,
                    "cik":              cik,
                    "accession_no":     acc_no,
                    "doc_name":         doc_name,   # filename from _id — use directly
                    "filed_at":         src.get("file_date", ""),
                    "period_of_report": src.get("period_of_report", ""),
                    "_raw_id":          file_id,
                })

            total       = data.get("hits", {}).get("total", {}).get("value", 0)
            from_offset += page_size
            if from_offset >= min(total, max_results):
                break

    return results[:max_results]


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
    cik_str  = cik.lstrip("0")
    base     = f"{EDGAR_BASE}/Archives/edgar/data/{cik_str}/{acc_path}"

    async with httpx.AsyncClient() as client:
        # Step 1: build candidate list — EFTS doc first, then index lookup, then fallbacks
        candidates: list[str] = []
        if doc_name:
            candidates.append(doc_name)
        index_names = await _fetch_filing_index(client, cik_str, acc_path, accession_no)
        for n in index_names:
            if n not in candidates:
                candidates.append(n)
        for n in _FALLBACK_XML_NAMES:
            if n not in candidates:
                candidates.append(n)

        # Step 2: try each candidate until we get a parseable infotable
        for fname in candidates:
            try:
                xml_text = await _get_text(client, f"{base}/{fname}")
            except Exception:
                continue
            holdings = _parse_infotable(xml_text)
            if holdings is not None:  # None = parse error; [] = no BDC match (still valid)
                return holdings

    return []


def _parse_infotable(xml_text: str) -> list[dict] | None:
    """
    Parse 13F infotable XML and return only BDC-related holdings.
    Returns None on parse error (so caller can try the next file).
    Returns [] if the file is valid but contains no BDC holdings.
    Handles both namespaced and non-namespaced variants of the schema.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
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
