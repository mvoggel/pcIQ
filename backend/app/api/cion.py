"""
/api/cion/funds — CION Investment Management fund intelligence.

Pulls live data from Yahoo Finance for CION's registered interval funds.
Unlike Form D (private placements), these are registered under the
Investment Company Act and trade via NAV on Nasdaq.
"""

import yfinance as yf
from fastapi import APIRouter

router = APIRouter(prefix="/api")

# CION's registered funds with context for the sales team
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


# Competitor registered funds — interval funds and BDCs in private credit
# same distribution channels as CION (iCapital, CAIS, wirehouses)
COMPETITOR_FUNDS = [
    {
        "ticker": "ASIF",
        "strategy": "Multi-asset credit — investment grade, high yield, loans, CLOs",
        "focus": "Private Credit",
    },
    {
        "ticker": "BCRED",
        "strategy": "Diversified credit — senior secured loans, bonds, structured credit",
        "focus": "Private Credit",
    },
    {
        "ticker": "ARCC",
        "strategy": "Middle market direct lending — first lien, second lien, subordinated debt",
        "focus": "Private Credit",
    },
    {
        "ticker": "OBDC",
        "strategy": "Upper middle market direct lending — senior secured, technology focus",
        "focus": "Private Credit",
    },
]


@router.get("/cion/competitors")
def get_competitor_funds() -> list[dict]:
    results = []
    for f in COMPETITOR_FUNDS:
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
