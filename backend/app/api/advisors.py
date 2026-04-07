"""
/api/advisors — Advisor-first intelligence endpoint.

Returns RIA profiles ranked by allocation activity and platform presence.
Unlike the fund-first /signals endpoint (which starts with a competitor fund
and finds who might buy it), this starts with the RIA and asks:
  "What is this advisor going to do next?"

Ranking uses a simple activity score:
  - Platform membership (each known platform = +3 pts)
  - Private fund AUM (> $100M = +2 pts)
  - AUM tier (log scale, 0–2 pts)

Data sources:
  - rias table: AUM, advisor count, location
  - ria_platforms: confirmed platform memberships
  - ria_fund_allocations: recent deal activity (if populated)
"""

import math
from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.db.client import get_db
from app.signals.run_signals import DEFAULT_TERRITORIES

router = APIRouter(prefix="/api")


def _aum_pts(aum: float | None) -> float:
    """0–2 pts on a log scale: 0 at $0, 1 at $1B, 2 at $10B+."""
    if not aum or aum <= 0:
        return 0.0
    return min(2.0, math.log10(aum / 1e9 + 0.01) + 2) / 2


def _aum_tier(aum: float | None) -> str:
    if aum is None:
        return "unknown"
    if aum >= 5e9:
        return "mega"
    if aum >= 1e9:
        return "large"
    if aum >= 500e6:
        return "mid"
    return "small"


def _fmt_aum(aum: float | None) -> str | None:
    if aum is None:
        return None
    if aum >= 1e9:
        return f"${aum / 1e9:.1f}B"
    if aum >= 1e6:
        return f"${aum / 1e6:.0f}M"
    return f"${aum:,.0f}"


@router.get("/advisors")
def get_advisors(
    territory: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    db = get_db()

    # ── 1. Determine state filter ──────────────────────────────────────
    states: list[str] = []
    if territory and territory in DEFAULT_TERRITORIES:
        states = DEFAULT_TERRITORIES[territory]

    # ── 2. Fetch RIAs with AUM (enriched ones only for a useful profile) ──
    query = (
        db.table("rias")
        .select(
            "id, crd_number, firm_name, city, state, aum, private_fund_aum, num_advisors"
        )
        .eq("is_active", True)
        .not_.is_("aum", "null")
        .order("aum", desc=True)
        .limit(500)  # over-fetch; we re-sort after scoring
    )
    if states:
        query = query.in_("state", states)

    ria_rows = query.execute().data or []

    if not ria_rows:
        return {"territory": territory or "All", "states": states, "total": 0, "advisors": []}

    # ── 3. Fetch platform memberships for these RIAs ───────────────────
    crd_set = [r["crd_number"] for r in ria_rows if r.get("crd_number")]
    # Supabase .in_() supports up to 500 values via PostgREST
    platforms_rows = (
        db.table("ria_platforms")
        .select("crd_number, platform_name, source")
        .in_("crd_number", crd_set[:500])
        .execute()
        .data or []
    )
    platforms_by_crd: dict[str, list[str]] = {}
    # source per platform: "csv" | "adv_brochure" | "edgar_inferred" | "scrape"
    platform_sources_by_crd: dict[str, dict[str, str]] = {}
    for p in platforms_rows:
        crd = p["crd_number"]
        name = p["platform_name"]
        src = p.get("source") or "edgar_inferred"
        platforms_by_crd.setdefault(crd, []).append(name)
        platform_sources_by_crd.setdefault(crd, {})[name] = src

    # ── 4. Fetch recent allocation counts ─────────────────────────────
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    ria_ids = [r["id"] for r in ria_rows]
    alloc_rows = (
        db.table("ria_fund_allocations")
        .select("ria_id")
        .gte("signal_date", cutoff)
        .in_("ria_id", ria_ids[:500])
        .execute()
        .data or []
    )
    alloc_count_by_id: dict[int, int] = {}
    for a in alloc_rows:
        rid = a["ria_id"]
        alloc_count_by_id[rid] = alloc_count_by_id.get(rid, 0) + 1

    # ── 5. Score and assemble ─────────────────────────────────────────
    advisors = []
    for r in ria_rows:
        crd = r.get("crd_number") or ""
        ria_id = r.get("id")
        aum = r.get("aum")
        private_fund_aum = r.get("private_fund_aum")
        platform_list = sorted(set(platforms_by_crd.get(crd, [])))
        platform_sources = platform_sources_by_crd.get(crd, {})
        allocation_count = alloc_count_by_id.get(ria_id, 0)

        score = (
            len(platform_list) * 3
            + (2 if private_fund_aum and private_fund_aum >= 1e8 else 0)
            + _aum_pts(aum) * 2
            + allocation_count * 4
        )

        advisors.append({
            "crd_number": crd,
            "firm_name": r.get("firm_name") or "",
            "city": r.get("city") or "",
            "state": r.get("state") or "",
            "aum": aum,
            "aum_fmt": _fmt_aum(aum),
            "aum_tier": _aum_tier(aum),
            "private_fund_aum": private_fund_aum,
            "private_fund_aum_fmt": _fmt_aum(private_fund_aum),
            "num_advisors": r.get("num_advisors"),
            "platforms": platform_list,
            "platform_sources": platform_sources,  # {platform: "csv"|"adv_brochure"|"edgar_inferred"}
            "platform_count": len(platform_list),
            "allocation_count_90d": allocation_count,
            "activity_score": round(score, 2),
        })

    advisors.sort(key=lambda x: x["activity_score"], reverse=True)
    advisors = advisors[:limit]

    return {
        "territory": territory or "All",
        "states": states,
        "total": len(advisors),
        "advisors": advisors,
    }
