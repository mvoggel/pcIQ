"""
ADV brochure platform scanner.

Scans Form ADV filings on EDGAR for mentions of alternative investment platforms
(iCapital, CAIS, Altigo, etc.) and writes confirmed platform relationships to
ria_platforms with source='adv_brochure'.

HOW IT WORKS
────────────
RIAs are required to file Form ADV annually with the SEC. Part 2A (the "brochure")
is a plain-English narrative where advisors describe their business — including which
technology platforms and distribution networks they use. A sentence like:

  "We use iCapital Network to facilitate client subscriptions to private funds."

…is a self-reported, SEC-filed statement. That's a meaningful signal — higher
confidence than our EDGAR feeder fund inference, lower than a verified directory CSV.

TWO COMPLEMENTARY PASSES
────────────────────────
Pass 1 — EDGAR EFTS bulk search (fast, ~2–5 min):
  Search EDGAR full-text index for ADV filings containing each keyword.
  Returns CIKs → resolve to CRDs via EDGAR submissions API → cross-reference
  against our rias table. Catches firms that uploaded their Part 2A to EDGAR.

Pass 2 — Direct IAPD brochure fetch (thorough, ~30–60 min):
  For RIAs in our rias table NOT caught by Pass 1, fetches their Part 2A brochure
  PDF directly from the IAPD file server and scans for keywords. Catches firms whose
  brochures live on IARD but aren't indexed in EDGAR EFTS.

Source tag written: 'adv_brochure'
Confidence vs other sources: csv > adv_brochure > scrape > edgar_inferred

Usage:
    make scan-brochures              # full scan (both passes)
    make scan-brochures DRY=1        # dry run — no DB writes, just print matches
    python -m app.ingestion.brochure_scanner --pass1-only   # EDGAR EFTS only
    python -m app.ingestion.brochure_scanner --pass2-only   # direct fetch only
    python -m app.ingestion.brochure_scanner --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import io
import re
import time
from collections import defaultdict

import httpx
import pdfplumber

from app.config import settings
from app.db.client import get_db
from app.db.writer import upsert_ria_platform

# ── platforms to scan for ─────────────────────────────────────────────────────

# Each entry: search_phrase → canonical platform name in ria_platforms
# Longer / more-specific phrases are checked first to avoid sub-string confusion.
PLATFORM_PHRASES: dict[str, str] = {
    "iCapital Network":    "iCapital",
    "iCapital":            "iCapital",
    "CAIS Group":          "CAIS",
    "CAIS platform":       "CAIS",
    "caisgroup.com":       "CAIS",
    "CAIS":                "CAIS",
    "Altigo":              "Altigo",
    "SEI Access":          "Altigo",   # Altigo was rebranded to SEI Access in 2024
    "Halo Investing":      "Halo",
    "Halo platform":       "Halo",
    "InvestX":             "InvestX",
    "Artivest":            "Artivest",
}

# Canonical platform names that ARE themselves platforms — exclude self-matches
# (e.g. iCapital's own ADV filing should not create an iCapital→iCapital row)
_PLATFORM_OWN_NAMES = {
    "icapital", "cais group", "altigo", "sei access", "halo investing", "investx", "artivest",
}

# EDGAR endpoints — same infrastructure used by run_feeder.py and edgar_client.py
_EFTS_BASE        = "https://efts.sec.gov"
_SUBMISSIONS_BASE = "https://data.sec.gov"
_IAPD_FILES_BASE  = "https://files.adviserinfo.sec.gov"
_IAPD_API_BASE    = "https://api.adviserinfo.sec.gov"

_EDGAR_HEADERS = {
    "User-Agent": settings.edgar_user_agent,
    "Accept": "application/json",
}
_IAPD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.adviserinfo.sec.gov/",
    "Origin": "https://www.adviserinfo.sec.gov",
}

_CONCURRENCY = 8
_DELAY       = 0.15    # seconds between requests (SEC rate limit: max 10 req/s)


# ── helpers ───────────────────────────────────────────────────────────────────

def _canonical_platform(text: str) -> str | None:
    """
    Check text for known platform phrases. Returns canonical platform name or None.
    Checks longer phrases first (dict insertion order preserved in Python 3.7+).
    """
    lower = text.lower()
    for phrase, canonical in PLATFORM_PHRASES.items():
        if phrase.lower() in lower:
            return canonical
    return None


def _is_platform_itself(firm_name: str) -> bool:
    """Return True if the filing is from a platform company, not an RIA using it."""
    lower = firm_name.lower()
    return any(own in lower for own in _PLATFORM_OWN_NAMES)


async def _get_json(client: httpx.AsyncClient, url: str, headers: dict, params: dict | None = None) -> dict:
    resp = await client.get(url, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    await asyncio.sleep(_DELAY)
    return resp.json()


# ── pass 1: EDGAR EFTS bulk search ───────────────────────────────────────────

async def _efts_search_adv(keyword: str, max_hits: int = 500) -> list[dict]:
    """
    Search EDGAR full-text index for ADV filings containing `keyword`.
    Returns list of {cik, firm_name, accession_no}.
    Searches last 2 years of filings (Part 2A is filed annually — 2 years
    ensures we catch firms with December fiscal year ends).
    """
    url = f"{_EFTS_BASE}/LATEST/search-index"
    results: list[dict] = []
    from_offset = 0
    page_size = 100

    async with httpx.AsyncClient() as client:
        while len(results) < max_hits:
            params = {
                "q":                      f'"{keyword}"',
                "forms":                  "ADV",
                "dateRange":              "custom",
                "startdt":                "2024-01-01",
                "from":                   from_offset,
                "hits.hits.total.value":  "true",
            }
            try:
                data = await _get_json(client, url, _EDGAR_HEADERS, params)
            except Exception:
                break

            hits = data.get("hits", {}).get("hits", [])
            total = data.get("hits", {}).get("total", {}).get("value", 0)
            if not hits:
                break

            for hit in hits:
                src = hit.get("_source", {})
                display_names = src.get("display_names") or []
                raw_name = display_names[0] if display_names else ""
                # Strip trailing "(CIK 0001234567)"
                firm_name = re.sub(r"\s*\(CIK\s*\d+\)\s*$", "", raw_name).strip()

                ciks = src.get("ciks") or []
                cik = str(ciks[0]).lstrip("0") if ciks else ""
                accession_no = src.get("adsh", "")

                if not cik:
                    continue
                if _is_platform_itself(firm_name):
                    continue

                results.append({
                    "cik":          cik,
                    "firm_name":    firm_name,
                    "accession_no": accession_no,
                    "platform":     PLATFORM_PHRASES.get(keyword, keyword),
                })

            from_offset += page_size
            if from_offset >= total or from_offset >= max_hits:
                break

    return results


async def _cik_to_crd(cik: str, sem: asyncio.Semaphore) -> str | None:
    """
    Resolve a CIK to a CRD number via the EDGAR submissions API.
    Returns CRD string or None.
    """
    padded = cik.zfill(10)
    url = f"{_SUBMISSIONS_BASE}/submissions/CIK{padded}.json"
    async with sem:
        try:
            async with httpx.AsyncClient() as client:
                data = await _get_json(client, url, _EDGAR_HEADERS)
            return str(data.get("crdNumber") or "").strip() or None
        except Exception:
            return None


async def run_pass1(
    our_crds: set[str],
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, list[str]]:
    """
    Pass 1: EDGAR EFTS search.
    Returns dict of {crd → [platform1, platform2, ...]} for RIAs in our DB.
    """
    print("\n── Pass 1: EDGAR EFTS full-text search ──────────────────────────────")

    # Collect all EFTS hits per unique keyword phrase
    all_hits: list[dict] = []
    seen_cik_platform: set[tuple[str, str]] = set()

    search_phrases = list(dict.fromkeys(PLATFORM_PHRASES.keys()))  # dedupe, preserve order
    for phrase in search_phrases:
        canonical = PLATFORM_PHRASES[phrase]
        try:
            hits = await _efts_search_adv(phrase, max_hits=500)
        except Exception as exc:
            print(f"  ✗  EFTS search failed for '{phrase}': {exc}")
            continue

        new_hits = 0
        for h in hits:
            key = (h["cik"], canonical)
            if key not in seen_cik_platform:
                seen_cik_platform.add(key)
                h["platform"] = canonical
                all_hits.append(h)
                new_hits += 1

        if new_hits:
            print(f"  '{phrase}' → {new_hits} unique CIKs in ADV filings")

    if not all_hits:
        print("  No EDGAR EFTS hits — Part 2A brochures may not be indexed. Pass 2 will cover these.")
        return {}

    print(f"\n  Resolving {len(all_hits)} CIKs → CRDs via EDGAR submissions API...")
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _resolve(hit: dict) -> tuple[str | None, dict]:
        crd = await _cik_to_crd(hit["cik"], sem)
        return crd, hit

    tasks = [asyncio.create_task(_resolve(h)) for h in all_hits]
    matched: dict[str, list[str]] = defaultdict(list)   # crd → [platforms]
    resolved = 0
    in_our_db = 0

    for fut in asyncio.as_completed(tasks):
        crd, hit = await fut
        resolved += 1
        if not crd:
            continue
        if crd not in our_crds:
            continue
        in_our_db += 1
        platform = hit["platform"]
        if platform not in matched[crd]:
            matched[crd].append(platform)
            if verbose:
                print(f"    ✓  CRD {crd} ({hit['firm_name']}) → {platform}")

        print(f"  Resolved {resolved}/{len(all_hits)} | In our DB: {in_our_db}", end="\r", flush=True)

    print()
    print(f"\n  Pass 1 result: {in_our_db} RIAs in our DB with ADV platform mentions")

    if not dry_run:
        written = 0
        for crd, platforms in matched.items():
            for platform in platforms:
                try:
                    upsert_ria_platform(crd, platform, source="adv_brochure")
                    written += 1
                except Exception as exc:
                    if verbose:
                        print(f"  ✗  DB write failed {crd}/{platform}: {exc}")
        print(f"  Wrote {written} rows to ria_platforms (source='adv_brochure')")
    else:
        print("  Dry run — skipping DB writes")

    return dict(matched)


# ── pass 2: direct IAPD brochure PDF fetch ───────────────────────────────────

async def _fetch_brochure_version_id(crd: str) -> str | None:
    """
    Try to get the current Part 2A brochure version ID for a CRD via IAPD API.
    Returns version ID string or None.
    """
    # The IAPD search API returns brochure version info in its response
    url = f"{_IAPD_API_BASE}/search/firm"
    params = {"query": crd, "hl": "false", "nrows": "1", "start": "0"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=_IAPD_HEADERS, params=params)
            if resp.status_code != 200:
                return None
            await asyncio.sleep(_DELAY)
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for hit in hits:
                src = hit.get("_source", {})
                if str(src.get("firm_source_id", "")) == str(crd):
                    # Look for brochure version ID in known field paths
                    brochure_id = (
                        src.get("brochure_version_id")
                        or src.get("brchr_vrsn_id")
                        or src.get("latestBrochureVersionId")
                    )
                    if brochure_id:
                        return str(brochure_id)
    except Exception:
        pass
    return None


async def _fetch_brochure_pdf_text(version_id: str) -> str | None:
    """Download the Part 2A brochure PDF and extract its text."""
    url = (
        f"{_IAPD_FILES_BASE}/IAPD/Content/Common/"
        f"crd_iapd_Brochure.aspx?BRCHR_VRSN_ID={version_id}"
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get(url, headers=_IAPD_HEADERS)
            if resp.status_code != 200:
                return None
            pdf_bytes = resp.content
        # Parse PDF in thread to avoid blocking the event loop
        def _extract(b: bytes) -> str:
            with pdfplumber.open(io.BytesIO(b)) as pdf:
                return "\n".join(
                    page.extract_text() or ""
                    for page in pdf.pages[:30]   # Part 2A rarely exceeds 30 pages
                )
        return await asyncio.to_thread(_extract, pdf_bytes)
    except Exception:
        return None


async def _scan_one_brochure(
    crd: str,
    sem: asyncio.Semaphore,
) -> tuple[str, list[str]]:
    """
    Fetch and scan the Part 2A brochure for one RIA.
    Returns (crd, [matched_platforms]).
    """
    async with sem:
        version_id = await _fetch_brochure_version_id(crd)
        if not version_id:
            return crd, []

        text = await _fetch_brochure_pdf_text(version_id)
        if not text:
            return crd, []

        found: list[str] = []
        for phrase, canonical in PLATFORM_PHRASES.items():
            if phrase.lower() in text.lower() and canonical not in found:
                found.append(canonical)

        return crd, found


async def run_pass2(
    our_crds: set[str],
    already_found: set[str],   # CRDs matched in pass 1 — skip if already confirmed
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, list[str]]:
    """
    Pass 2: direct IAPD brochure PDF fetch for RIAs not caught by Pass 1.
    """
    remaining = [c for c in our_crds if c not in already_found]
    print(f"\n── Pass 2: Direct IAPD brochure scan ({len(remaining)} RIAs) ──────────────")

    if not remaining:
        print("  All RIAs already covered by Pass 1.")
        return {}

    est_min = len(remaining) * 2 // (_CONCURRENCY * 60)
    print(f"  Estimated time: ~{max(1, est_min)} min  |  concurrency={_CONCURRENCY}")
    print(f"  (Many will return quickly — state-registered firms have no IAPD brochure)\n")

    sem = asyncio.Semaphore(_CONCURRENCY)
    matched: dict[str, list[str]] = defaultdict(list)
    total = len(remaining)
    done = 0
    hits = 0
    start = time.monotonic()

    async def _staggered(crd: str, i: int):
        await asyncio.sleep(i * 0.05)   # gentle stagger
        return await _scan_one_brochure(crd, sem)

    tasks = [asyncio.create_task(_staggered(crd, i)) for i, crd in enumerate(remaining)]

    for fut in asyncio.as_completed(tasks):
        crd, platforms = await fut
        done += 1
        if platforms:
            hits += 1
            matched[crd] = platforms
            if verbose:
                print(f"\n  ✓  CRD {crd} → {', '.join(platforms)}")

        elapsed = time.monotonic() - start
        rate = done / elapsed if elapsed > 0 else 1
        eta_s = (total - done) / rate if rate > 0 else 0
        bar = "█" * int(30 * done / total) + "░" * (30 - int(30 * done / total))
        print(
            f"  [{bar}] {done/total*100:4.0f}%  {hits} matches  eta {eta_s/60:.0f}m",
            end="\r", flush=True,
        )

    elapsed = time.monotonic() - start
    print(f"\n\n  Pass 2 result: {hits} additional RIAs with brochure platform mentions")
    print(f"  Completed in {elapsed/60:.1f} min")

    if not dry_run and matched:
        written = 0
        for crd, platforms in matched.items():
            for platform in platforms:
                try:
                    upsert_ria_platform(crd, platform, source="adv_brochure")
                    written += 1
                except Exception as exc:
                    if verbose:
                        print(f"  ✗  DB write {crd}/{platform}: {exc}")
        print(f"  Wrote {written} rows to ria_platforms (source='adv_brochure')")
    elif dry_run and matched:
        print("  Dry run — skipping DB writes")

    return dict(matched)


# ── main ─────────────────────────────────────────────────────────────────────

async def run(
    pass1: bool = True,
    pass2: bool = True,
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    db = get_db()

    # Load all CRD numbers from our rias table
    rows = db.table("rias").select("crd_number").eq("is_active", True).execute()
    our_crds: set[str] = {r["crd_number"] for r in (rows.data or []) if r.get("crd_number")}
    print(f"\npcIQ ADV brochure scanner")
    print(f"  {len(our_crds):,} active RIAs in DB | dry_run={dry_run} | pass1={pass1} | pass2={pass2}")

    p1_matched: dict[str, list[str]] = {}
    if pass1:
        p1_matched = await run_pass1(our_crds, dry_run=dry_run, verbose=verbose)

    p2_matched: dict[str, list[str]] = {}
    if pass2:
        already_confirmed = set(p1_matched.keys())
        p2_matched = await run_pass2(our_crds, already_confirmed, dry_run=dry_run, verbose=verbose)

    # Summary
    all_matched = {**p1_matched, **p2_matched}
    platform_counts: dict[str, int] = defaultdict(int)
    for platforms in all_matched.values():
        for p in platforms:
            platform_counts[p] += 1

    print(f"\n{'─'*60}")
    print(f"  Total RIAs with brochure platform mentions: {len(all_matched)}")
    for platform, count in sorted(platform_counts.items(), key=lambda x: -x[1]):
        print(f"    {platform}: {count}")
    if not dry_run and all_matched:
        print(f"\n  All written to ria_platforms with source='adv_brochure'")
        print(f"  These will appear in FundModal Confirmed Allocators section.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="pcIQ — ADV Part 2 brochure platform scanner"
    )
    parser.add_argument("--pass1-only", action="store_true", help="EDGAR EFTS search only")
    parser.add_argument("--pass2-only", action="store_true", help="Direct brochure fetch only")
    parser.add_argument("--dry-run",    action="store_true", help="No DB writes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each match")
    args = parser.parse_args()

    p1 = not args.pass2_only
    p2 = not args.pass1_only

    asyncio.run(run(pass1=p1, pass2=p2, dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
