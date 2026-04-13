"""
/api/cion/* — CION Investment Management fund intelligence.

Pulls live data from Yahoo Finance for CION's registered interval funds and
portfolio health metrics from SEC EDGAR N-PORT filings.
"""

import re
import time
import xml.etree.ElementTree as ET

import requests
import yfinance as yf
from fastapi import APIRouter

from app.db.client import get_db

router = APIRouter(prefix="/api")

# ── EDGAR N-PORT pipeline ────────────────────────────────────────────────────

# CIK numbers sourced from EDGAR company search.
# CGIQX is a feeder → master fund structure; we use the master fund CIK
# (0002001586) so we get all 94 real holdings instead of just one entry.
_FUND_CIKS = {
    "CADUX": "1678124",   # CION Ares Diversified Credit Fund
    "CGIQX": "2001586",   # CION Grosvenor Infrastructure Master Fund
}

# EDGAR requires a descriptive User-Agent per their access guidelines
_EDGAR_HEADERS = {
    "User-Agent": "pcIQ platform contact@pciq.com",
    "Accept-Encoding": "gzip, deflate",
}

# Simple in-memory cache — N-PORT only updates quarterly, so 6 h is fine
_nport_cache: dict[str, tuple[float, dict]] = {}
_NPORT_TTL = 6 * 3600  # seconds


def _strip_ns(tag: str) -> str:
    """Remove XML namespace prefix from a tag, e.g. {http://...}foo → foo."""
    return re.sub(r"\{[^}]+\}", "", tag)


def _find_text(node: ET.Element, *path: str) -> str | None:
    """
    Traverse a path of local tag names from node, ignoring XML namespaces.
    Returns the text of the final element or None if any step is missing.
    """
    current = node
    for part in path:
        match = next(
            (c for c in current if _strip_ns(c.tag) == part),
            None,
        )
        if match is None:
            return None
        current = match
    return current.text


def _iter_tag(node: ET.Element, tag: str):
    """Yield all descendants whose local tag name equals tag."""
    for el in node.iter():
        if _strip_ns(el.tag) == tag:
            yield el


def _fetch_nport_xml(cik: str) -> ET.Element:
    """Download and parse the most recent NPORT-P filing XML from EDGAR."""
    padded = cik.zfill(10)
    sub_url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    sub = requests.get(sub_url, headers=_EDGAR_HEADERS, timeout=15).json()

    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])

    acc = next(
        (accessions[i] for i, f in enumerate(forms) if f == "NPORT-P"),
        None,
    )
    if acc is None:
        raise ValueError(f"No NPORT-P filing found for CIK {cik}")

    acc_clean = acc.replace("-", "")
    xml_url = (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}"
        f"/{acc_clean}/primary_doc.xml"
    )
    resp = requests.get(xml_url, headers=_EDGAR_HEADERS, timeout=30)
    resp.raise_for_status()
    return ET.fromstring(resp.content)


def _parse_nport(root: ET.Element) -> dict:
    """
    Extract portfolio health metrics from an N-PORT XML element tree.

    Key fields returned:
      period          – reporting period end date (YYYY-MM-DD)
      net_assets      – total net assets in USD
      total_assets    – total assets in USD
      borrowings      – long-term bank borrowings in USD (leverage proxy)
      monthly_returns – list of up to 3 recent monthly total returns (pct)
      total_holdings  – number of portfolio positions
      debt_count      – number of debt/loan positions
      defaults        – positions with isDefault=Y
      arrears         – positions with areIntrstPmntsInArrs=Y
      pik_count       – positions paying PIK interest
      asset_categories – {category_code: count} breakdown
    """
    # ── Fund-level metadata ──────────────────────────────────────────────────
    period = _find_text(root, "formData", "genInfo", "repPdDate")

    def _float(path):
        v = _find_text(root, "formData", "fundInfo", path)
        return float(v) if v else None

    net_assets = _float("netAssets")
    total_assets = _float("totAssets")
    borrowings = _float("amtPayAftOneYrBanksBorr")

    # ── Monthly total returns (up to 3 months back) ──────────────────────────
    # N-PORT stores these as percentage values (e.g. 0.44 = 0.44 %)
    monthly_returns: list[float] = []
    for tag in ("rtn1", "rtn2", "rtn3"):
        el = next(_iter_tag(root, tag), None)
        if el is not None and el.text:
            try:
                monthly_returns.append(round(float(el.text), 4))
            except ValueError:
                pass

    # ── Holdings analysis ────────────────────────────────────────────────────
    holdings = list(_iter_tag(root, "invstOrSec"))
    total_holdings = len(holdings)

    defaults = 0
    arrears = 0
    pik_count = 0
    debt_count = 0
    asset_categories: dict[str, int] = {}

    for h in holdings:
        cat = _find_text(h, "assetCat") or "OTHER"
        asset_categories[cat] = asset_categories.get(cat, 0) + 1

        debt_node = next(_iter_tag(h, "debtSec"), None)
        if debt_node is not None:
            debt_count += 1
            if _find_text(debt_node, "isDefault") == "Y":
                defaults += 1
            if _find_text(debt_node, "areIntrstPmntsInArrs") == "Y":
                arrears += 1
            if _find_text(debt_node, "isPaidKind") == "Y":
                pik_count += 1

    return {
        "period": period,
        "net_assets": net_assets,
        "total_assets": total_assets,
        "borrowings": borrowings,
        "monthly_returns": monthly_returns,
        "total_holdings": total_holdings,
        "debt_count": debt_count,
        "defaults": defaults,
        "arrears": arrears,
        "pik_count": pik_count,
        "asset_categories": asset_categories,
    }


@router.get("/cion/nport-metrics")
def get_nport_metrics() -> dict:
    """
    Portfolio health metrics sourced directly from SEC EDGAR N-PORT filings.

    Data is cached for 6 hours because N-PORT only updates quarterly.
    On cache miss the EDGAR HTTP calls take ~3–5 s total.
    """
    now = time.time()
    result: dict[str, dict] = {}

    for ticker, cik in _FUND_CIKS.items():
        cache_key = f"nport_{cik}"
        if cache_key in _nport_cache:
            cached_at, cached_data = _nport_cache[cache_key]
            if now - cached_at < _NPORT_TTL:
                result[ticker] = cached_data
                continue

        try:
            xml_root = _fetch_nport_xml(cik)
            metrics = _parse_nport(xml_root)
            _nport_cache[cache_key] = (now, metrics)
            result[ticker] = metrics
        except Exception as e:
            result[ticker] = {"error": str(e)}

    return result


# ── CION own funds (Yahoo Finance) ───────────────────────────────────────────

CION_FUNDS = [
    {
        "ticker": "CADUX",
        "strategy": "Diversified credit — senior secured loans, bonds, structured credit",
        "focus": "Private Credit",
    },
    {
        "ticker": "CGIQX",
        "strategy": "Global infrastructure equity and debt across energy, transport, utilities",
        "focus": "Infrastructure",
    },
]


def _build_fund(ticker_sym: str, strategy: str, focus: str) -> dict:
    tk = yf.Ticker(ticker_sym)
    info = tk.info

    # 90-day price history for sparkline
    hist = tk.history(period="3mo")
    sparkline: list[float] = []
    if not hist.empty:
        sparkline = [round(float(v), 4) for v in hist["Close"].dropna().tolist()]

    nav = info.get("regularMarketPrice")
    nav_prev = info.get("regularMarketPreviousClose")
    nav_change = info.get("regularMarketChange")
    nav_change_pct = info.get("regularMarketChangePercent")

    return {
        "ticker": ticker_sym,
        "name": info.get("longName") or info.get("shortName") or ticker_sym,
        "strategy": strategy,
        "focus": focus,
        "exchange": info.get("fullExchangeName", "Nasdaq"),
        "currency": info.get("currency", "USD"),
        # Current NAV
        "nav": nav,
        "nav_prev_close": nav_prev,
        "nav_change": round(nav_change, 4) if nav_change is not None else None,
        "nav_change_pct": round(nav_change_pct, 4) if nav_change_pct is not None else None,
        # Performance
        "fifty_two_week_change_pct": info.get("fiftyTwoWeekChangePercent"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "fifty_day_avg": info.get("fiftyDayAverage"),
        "two_hundred_day_avg": info.get("twoHundredDayAverage"),
        # Financial performance enrichment (may be sparse for non-traded funds)
        "total_assets": info.get("totalAssets"),
        "distribution_yield": info.get("yield") or info.get("dividendYield"),
        "ytd_return": info.get("ytdReturn"),
        "three_year_return": info.get("threeYearAverageReturn"),
        # Sparkline (90 days of daily NAV)
        "sparkline": sparkline,
    }


@router.get("/cion/funds")
def get_cion_funds() -> list[dict]:
    results = []
    for f in CION_FUNDS:
        try:
            results.append(_build_fund(f["ticker"], f["strategy"], f["focus"]))
        except Exception as e:
            results.append({
                "ticker": f["ticker"],
                "name": f["ticker"],
                "strategy": f["strategy"],
                "focus": f["focus"],
                "error": str(e),
            })
    return results


# ── Platform stats ───────────────────────────────────────────────────────────

@router.get("/cion/platform-stats")
def get_platform_stats() -> dict:
    """
    Live platform coverage stats for the CION IQ page callout bar.
    Returns counts directly from Supabase so the UI never shows stale numbers.
    """
    db = get_db()

    ria_res = (
        db.table("rias")
        .select("*", count="exact")
        .eq("is_active", True)
        .execute()
    )
    ria_count = ria_res.count or 0

    aum_rows = (
        db.table("rias")
        .select("aum")
        .eq("is_active", True)
        .not_.is_("aum", "null")
        .execute()
    ).data or []
    total_aum = sum(r["aum"] for r in aum_rows if r.get("aum"))

    def _fmt_aum(v: float) -> str:
        if v >= 1e12:
            return f"${v / 1e12:.1f}T"
        if v >= 1e9:
            return f"${v / 1e9:.0f}B"
        return f"${v / 1e6:.0f}M"

    state_rows = (
        db.table("rias")
        .select("state")
        .eq("is_active", True)
        .not_.is_("state", "null")
        .execute()
    ).data or []
    states = len({r["state"] for r in state_rows if r.get("state")})

    feeder_res = (
        db.table("feeder_funds")
        .select("*", count="exact")
        .execute()
    )
    feeder_count = feeder_res.count or 0

    return {
        "rias_tracked": ria_count,
        "aum_represented": _fmt_aum(total_aum) if total_aum else "$0",
        "states_covered": states,
        "feeder_funds": feeder_count,
    }
