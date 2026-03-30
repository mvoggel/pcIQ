"""
Form ADV parser.

Converts raw IAPD API JSON into a typed RIA model.

IAPD firm detail JSON structure (key paths):
  hits.hits[0]._source.currentAum          → total AUM
  hits.hits[0]._source.prtclPrsnCount      → number of principals
  hits.hits[0]._source.registrtnCnt        → registration count

For the firm detail endpoint (/api/Firm/{crd}), the response contains:
  basicInformation.firmName
  basicInformation.crdNumber
  basicInformation.totalAssets (AUM in dollars)
  basicInformation.totalAccounts
  businessAddress.city / state / zip
  registrations[].regAuthority  ("SEC" for SEC-registered)
  iardInformation.totalEmpCount
  iardInformation.investmentAdvisoryCount
  iardInformation.totalAssetsUnderMgmt
  iardInformation.totalAccountsUnderMgmt
  iardInformation.discretionaryAum
  iardInformation.nonDiscretionaryAum
  privateFundInfo.totalPrivateFundAum  (if available)

Note: IAPD field names and structure vary across firm types.
We use .get() everywhere and default to None — never raise on missing fields.
"""

from datetime import date

from app.models.ria import RIA


def parse_edgar_submissions(data: dict, crd_number: str = "") -> RIA | None:
    """
    Parse EDGAR submissions JSON (data.sec.gov) into a minimal RIA record.
    Less rich than IAPD — gives us name, CIK, state, and filing dates.
    Used as fallback when IAPD is unavailable.
    """
    if not data:
        return None

    firm_name = (data.get("name") or "").strip()
    if not firm_name:
        return None

    cik = str(data.get("cik") or "").strip()
    state = str(data.get("stateOfIncorporation") or "").strip().upper()[:2]
    city = ""
    zip_code = ""

    # addresses block
    addresses = data.get("addresses") or {}
    biz = addresses.get("business") or {}
    city = (biz.get("city") or "").strip().title()
    state = state or (biz.get("stateOrCountry") or "").strip().upper()[:2]
    zip_code = str(biz.get("zipCode") or "").strip()
    website = (data.get("website") or "").strip()

    # Most recent ADV filing date
    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    filed_at = None
    for form, d in zip(forms, dates):
        if "ADV" in str(form).upper():
            filed_at = _to_date(d)
            break

    if not crd_number:
        crd_number = str(data.get("crdNumber") or "")

    return RIA(
        crd_number=crd_number,
        cik=cik,
        firm_name=firm_name,
        city=city,
        state=state,
        zip_code=zip_code,
        website=website,
        adv_filed_at=filed_at,
    )


def parse_iapd_firm(data: dict, crd_number: str) -> RIA | None:
    """
    Parse IAPD firm detail JSON into an RIA model.

    Args:
        data:       Raw JSON dict from /api/Firm/{crd}
        crd_number: The CRD number used to fetch this record

    Returns RIA or None if the data is too sparse to be useful.
    """
    if not data:
        return None

    # IAPD wraps results differently depending on endpoint version
    # Try both flat and nested structures
    firm = data.get("basicInformation") or data.get("iaFirmSummary") or data
    iard = data.get("iardInformation") or {}
    address = (
        data.get("businessAddress")
        or data.get("mainAddress")
        or firm.get("businessAddress")
        or {}
    )

    firm_name = (
        firm.get("firmName")
        or firm.get("orgNm")
        or data.get("firmName")
        or ""
    ).strip()

    if not firm_name:
        return None

    # AUM — try multiple field paths, IAPD is inconsistent
    aum = (
        _to_float(iard.get("totalAssetsUnderMgmt"))
        or _to_float(iard.get("discretionaryAum"))
        or _to_float(firm.get("totalAssets"))
        or _to_float(data.get("currentAum"))
    )

    private_fund_aum = _to_float(
        data.get("totalPrivateFundAum")
        or iard.get("totalPrivateFundAum")
    )

    num_accounts = (
        _to_int(iard.get("totalAccountsUnderMgmt"))
        or _to_int(firm.get("totalAccounts"))
    )

    num_employees = _to_int(iard.get("totalEmpCount") or firm.get("empCount"))
    num_advisors = _to_int(
        iard.get("investmentAdvisoryCount")
        or firm.get("iaCount")
    )

    state = (
        address.get("state")
        or address.get("stateOrCountry")
        or address.get("st")
        or ""
    ).upper()[:2]

    city = (address.get("city") or address.get("cty") or "").strip().title()
    zip_code = str(address.get("zipCode") or address.get("zip") or "").strip()
    website = (data.get("websiteAddress") or firm.get("websiteAddress") or "").strip()

    cik = str(firm.get("cik") or data.get("cik") or "").strip()

    # Determine if SEC-registered (vs. state-registered)
    registrations = data.get("registrations") or []
    is_sec = any(
        "SEC" in str(r.get("regAuthority", "")).upper()
        for r in registrations
    ) if registrations else True  # assume SEC if we fetched from IAPD

    # Filed date
    filed_str = data.get("lastUpdated") or iard.get("lastUpdatedDate") or ""
    filed_at = _to_date(filed_str)

    return RIA(
        crd_number=str(crd_number),
        cik=cik,
        firm_name=firm_name,
        aum=aum,
        private_fund_aum=private_fund_aum,
        num_accounts=num_accounts,
        num_employees=num_employees,
        num_investment_advisors=num_advisors,
        city=city,
        state=state,
        zip_code=zip_code,
        website=website,
        is_sec_registered=is_sec,
        adv_filed_at=filed_at,
    )


def _to_float(val) -> float | None:
    if val in (None, "", "N/A", 0):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _to_int(val) -> int | None:
    if val in (None, "", "N/A"):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _to_date(val: str) -> date | None:
    if not val:
        return None
    # IAPD uses formats like "2025-01-15", "01/15/2025", "2025-01-15T00:00:00"
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            from datetime import datetime
            return datetime.strptime(val[:10], fmt[:8] if "T" in val else fmt).date()
        except ValueError:
            continue
    return None
