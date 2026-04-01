"""
ADV enrichment cache — read/write to the adv_enrichment Supabase table.

Cache TTL: 30 days. ADV is filed annually so this is conservative.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.db.client import get_db
from app.ingestion.adv_pdf_parser import ADVData

_TTL_DAYS = 30


def _is_fresh(fetched_at_str: str | None) -> bool:
    if not fetched_at_str:
        return False
    try:
        fetched_at = datetime.fromisoformat(fetched_at_str.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - fetched_at < timedelta(days=_TTL_DAYS)
    except Exception:
        return False


def get_cached_adv(crd: str) -> ADVData | None:
    """Return cached ADVData if present and fresh, else None."""
    try:
        db = get_db()
        result = (
            db.table("adv_enrichment")
            .select("*")
            .eq("crd", crd)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if not _is_fresh(row.get("fetched_at")):
            return None

        client_types_raw = row.get("client_types") or []
        if isinstance(client_types_raw, str):
            client_types_raw = json.loads(client_types_raw)

        adv = ADVData(crd=crd)
        adv.firm_name = row.get("firm_name") or ""
        adv.total_aum = row.get("total_aum")
        adv.discretionary_aum = row.get("discretionary_aum")
        adv.total_clients = row.get("total_clients")
        adv.total_employees = row.get("total_employees")
        adv.investment_advisory_employees = row.get("investment_advisory_employees")
        # Rebuild client_types dict from cached [{label, clients, aum}] list
        adv.client_types = {
            ct["label"]: {"clients": ct.get("clients"), "aum": ct.get("aum")}
            for ct in client_types_raw
            if isinstance(ct, dict) and "label" in ct
        }
        return adv
    except Exception:
        return None


def set_cached_adv(adv: ADVData) -> None:
    """Upsert ADVData into the cache table."""
    try:
        db = get_db()
        client_types_list = [
            {"label": label, "clients": vals.get("clients"), "aum": vals.get("aum")}
            for label, vals in (adv.client_types or {}).items()
        ]
        db.table("adv_enrichment").upsert(
            {
                "crd": adv.crd,
                "firm_name": adv.firm_name or "",
                "total_aum": adv.total_aum,
                "discretionary_aum": adv.discretionary_aum,
                "total_clients": adv.total_clients,
                "total_employees": adv.total_employees,
                "investment_advisory_employees": adv.investment_advisory_employees,
                "client_types": client_types_list,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="crd",
        ).execute()
    except Exception:
        pass  # cache write failure is non-fatal
