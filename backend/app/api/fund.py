"""
/api/fund/{cik}/{accession_no} — enriched fund detail for the modal.

Combines four sources:
  1. DB row  — investors, exemptions, amount sold (already stored, just not surfaced)
  2. Form D XML — related persons / GP names (parsed live, ~200ms)
  3. EDGAR submissions API — website, phone, SIC description (free, ~150ms)
  4. IAPD search — affiliated investment adviser, CRD number, AUM, client count
"""

import asyncio
import re

import httpx
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db.adv_cache import get_cached_adv, set_cached_adv
from app.db.client import get_db
from app.ingestion.adv_pdf_parser import fetch_adv_data
from app.ingestion.edgar_client import fetch_form_d_xml
from app.ingestion.form_d_parser import parse_form_d

router = APIRouter(prefix="/api")

# Human-readable labels for Reg D federal exemption codes
EXEMPTION_LABELS: dict[str, str] = {
    "06b": "Rule 506(b) — Private placement (up to 35 non-accredited investors)",
    "06c": "Rule 506(c) — General solicitation (accredited investors only)",
    "3C.1": "Section 3(c)(1) — Up to 100 beneficial owners",
    "3C.7": "Section 3(c)(7) — Qualified purchasers only ($5M+ investable assets)",
    "3C":   "Section 3(c) — Investment company exemption",
    "04a6": "Rule 4(a)(6) — Crowdfunding",
    "04a5": "Rule 4(a)(5) — Accredited investor only",
}


_IAPD_SEARCH_URL = "https://api.adviserinfo.sec.gov/search/firm"
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

# Fund-specific words that don't help identify the manager firm
_FUND_WORDS = {
    "fund", "clo", "bdc", "trust", "reit", "opportunity", "income",
    "real", "estate", "private", "equity", "debt", "senior", "secured",
    "direct", "lending", "infrastructure", "growth", "credit", "alternative",
    "alternatives", "loan", "mortgage", "finance", "financial",
}
_LEGAL_SUFFIXES = {"llc", "lp", "ltd", "inc", "llp", "plc", "co", "corp", "corporation"}


def _manager_search_term(entity_name: str) -> str:
    """
    Extract a brand-level search term from a fund entity name.
    'Blue Owl CLO 15, Ltd'  → 'Blue Owl'
    'Ares Capital Corp III'  → 'Ares'
    'KKR Real Estate Finance' → 'KKR'
    """
    # Strip punctuation and roman numeral / number suffixes
    cleaned = re.sub(r"[,\.]", "", entity_name)
    cleaned = re.sub(
        r"\b(xv|xiv|xiii|xii|xi|ix|viii|vii|vi|iv|iii|ii|\d+)\b",
        "", cleaned, flags=re.IGNORECASE
    ).strip()

    brand: list[str] = []
    for word in cleaned.split():
        w = word.lower()
        if w in _LEGAL_SUFFIXES or w in _FUND_WORDS:
            if brand:
                break  # stop collecting once we hit a fund/legal word
        else:
            brand.append(word)

    result = " ".join(brand[:3]).strip()
    return result if result else entity_name.split()[0]


import json as _json


def _parse_iapd_address(addr_json: str) -> tuple[str, str, str]:
    """Parse IAPD's firm_ia_address_details JSON string → (city, state, phone)."""
    if not addr_json:
        return ("", "", "")
    try:
        d = _json.loads(addr_json)
        office = d.get("officeAddress") or {}
        city  = str(office.get("city")  or "").strip().title()
        state = str(office.get("state") or "").strip().upper()
        phone = str(d.get("businessPhoneNumber") or "").strip()
        return (city, state, phone)
    except Exception:
        return ("", "", "")


async def _search_iapd_manager(entity_name: str) -> dict | None:
    """
    Search IAPD for the investment adviser affiliated with this fund.
    Uses the public /search/firm endpoint — no auth, no detail-endpoint needed.

    IAPD search returns IA-specific records with fields:
      firm_source_id         → CRD number
      firm_name              → registered name
      firm_ia_full_sec_number → e.g. "801-63800" (confirms SEC registration)
      firm_ia_scope          → ACTIVE / INACTIVE
      firm_ia_address_details → JSON string with city/state/phone
      firm_other_names       → relying advisers + DBA names
      firm_branches_count    → number of branches

    Note: AUM is NOT returned in search results — it requires the blocked
    detail endpoint. We surface the IAPD profile link instead so users can
    click through to the full record.
    """
    query = _manager_search_term(entity_name)
    if not query:
        return None

    params = {"query": query, "hl": "false", "nrows": "5", "start": "0"}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                _IAPD_SEARCH_URL, headers=_IAPD_HEADERS, params=params
            )
            if resp.status_code != 200:
                return None

            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                return None

            # Score each hit to find the best match:
            #   - Must be an IA record (has firm_ia_scope)
            #   - Must be ACTIVE
            #   - Prefer the largest firm (most firm_other_names = most relying advisers)
            #   - Bonus for exact brand-word prefix match
            brand_word = query.lower().split()[0]

            def _score(src: dict) -> int:
                if "firm_ia_scope" not in src:
                    return -1000          # BD-only record — skip
                if str(src.get("firm_ia_scope") or "").upper() != "ACTIVE":
                    return -500           # Inactive — heavily penalize
                name = str(src.get("firm_name") or "").lower()
                other_names: list = src.get("firm_other_names") or []
                relying = sum(1 for n in other_names if "RELYING" in n.upper())
                prefix_bonus = 100 if name.startswith(brand_word) else 0
                return relying + prefix_bonus

            srcs = [h.get("_source", {}) for h in hits]
            srcs.sort(key=_score, reverse=True)
            best = srcs[0] if srcs and _score(srcs[0]) > -500 else None
            if best is None:
                # Last resort: any IA record
                for src in srcs:
                    if "firm_ia_scope" in src:
                        best = src
                        break
            if best is None:
                best = hits[0].get("_source", {})

            crd = str(best.get("firm_source_id") or "").strip()
            if not crd:
                return None

            firm_name = str(best.get("firm_name") or "").strip().title()
            scope = str(best.get("firm_ia_scope") or best.get("firm_scope") or "").strip()
            sec_number = str(best.get("firm_ia_full_sec_number") or "").strip()
            branches = best.get("firm_branches_count")

            # Count relying advisers from firm_other_names (tagged "(Relying Adviser)")
            other_names: list[str] = best.get("firm_other_names") or []
            relying_count = sum(
                1 for n in other_names if "RELYING ADVISER" in n.upper()
            )

            # Parse address JSON string
            addr_json = best.get("firm_ia_address_details") or best.get("firm_address_details") or ""
            city, state, phone = _parse_iapd_address(addr_json)

            return {
                "crd": crd,
                "firm_name": firm_name,
                "sec_number": sec_number,
                "scope": scope,          # "ACTIVE" | "INACTIVE"
                "city": city,
                "state": state,
                "phone": phone,
                "branches": int(branches) if branches is not None else None,
                "relying_advisers": relying_count,
                "iapd_url": f"https://adviserinfo.sec.gov/firm/summary/{crd}",
                "adv_pdf_url": f"https://reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf",
                "search_query": query,
            }
    except Exception:
        return None


async def _fetch_submissions(cik: str) -> dict:
    """Fetch company/fund metadata from EDGAR submissions API. Returns {} on failure."""
    padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    headers = {"User-Agent": settings.edgar_user_agent}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception:
        pass
    return {}


@router.get("/fund/{cik}/{accession_no}")
async def get_fund_detail(cik: str, accession_no: str) -> dict:
    """
    Return enriched fund data for the detail modal.
    Immediate DB fields + live XML parse for GPs + EDGAR submissions for metadata.
    """
    db = get_db()

    # 1. Pull full filing row from DB
    result = (
        db.table("form_d_filings")
        .select("*")
        .eq("cik", cik)
        .eq("accession_no", accession_no)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Filing not found in DB")
    row = result.data[0]

    entity_name = row["entity_name"] or ""

    # 2. Fetch XML + submissions + IAPD search (all parallel, ADV PDF added below)
    xml_task  = asyncio.create_task(fetch_form_d_xml(cik, accession_no))
    sub_task  = asyncio.create_task(_fetch_submissions(cik))
    iapd_task = asyncio.create_task(_search_iapd_manager(entity_name))

    related_persons: list[dict] = []
    try:
        xml = await xml_task
        filing = parse_form_d(xml, cik, accession_no)
        related_persons = [
            {
                "name": p.full_name,
                "relationships": p.relationship,
            }
            for p in filing.related_persons
            if p.full_name.strip()
        ]
    except Exception:
        pass

    submissions = await sub_task
    manager_intelligence = await iapd_task

    # 3. If IAPD match found, get ADV data — cache-first, live fetch on miss
    adv_data = None
    if manager_intelligence and manager_intelligence.get("crd"):
        crd = manager_intelligence["crd"]
        adv_data = get_cached_adv(crd)
        if adv_data is None:
            adv_data = await fetch_adv_data(crd, timeout=12.0)
            if adv_data:
                set_cached_adv(adv_data)
        if adv_data:
            manager_intelligence["aum"] = adv_data.total_aum
            manager_intelligence["discretionary_aum"] = adv_data.discretionary_aum
            manager_intelligence["total_clients"] = adv_data.total_clients
            manager_intelligence["total_employees"] = adv_data.total_employees
            manager_intelligence["investment_advisory_employees"] = adv_data.investment_advisory_employees
            manager_intelligence["client_types"] = [
                {
                    "label": label,
                    "clients": vals.get("clients"),
                    "aum": vals.get("aum"),
                }
                for label, vals in adv_data.client_types.items()
            ]
            manager_intelligence["adv_as_of"] = adv_data.pdf_url
    website = (submissions.get("website") or "").strip()
    phone = (submissions.get("phone") or "").strip()
    sic_desc = (submissions.get("sicDescription") or "").strip()

    # 3. Format exemptions with labels
    raw_exemptions: list[str] = row.get("federal_exemptions") or []
    exemptions = [
        {"code": code, "label": EXEMPTION_LABELS.get(code, code)}
        for code in raw_exemptions
    ]

    return {
        "cik": cik,
        "accession_no": accession_no,
        "entity_name": entity_name,
        "investment_fund_type": row["investment_fund_type"],
        "filed_at": row["filed_at"],
        "date_of_first_sale": row["date_of_first_sale"],
        "is_amendment": row["is_amendment"],
        "city": row["city"],
        "state_or_country": row["state_or_country"],
        "total_offering_amount": row["total_offering_amount"],
        "total_amount_sold": row["total_amount_sold"],
        "total_investors": row["total_investors"],
        "has_non_accredited": row["has_non_accredited"],
        "exemptions": exemptions,
        "related_persons": related_persons,
        "website": website,
        "phone": phone,
        "sic_description": sic_desc,
        "manager_intelligence": manager_intelligence,
    }
