"""
ADV Part 2A brochure platform scanner.

Scans Form ADV Part 2A brochures (the plain-English narrative each RIA files
annually with the SEC) for mentions of iCapital, CAIS, Altigo, etc.

A sentence like "We use iCapital Network to facilitate client subscriptions to
private funds" is a self-reported, SEC-filed statement — higher confidence than
our EDGAR feeder fund inference, lower than a verified directory CSV.

Source tag written: 'adv_brochure'
Confidence ranking: csv > adv_brochure > scrape > edgar_inferred

WHY PASS 1 (EDGAR EFTS) DOESN'T WORK
──────────────────────────────────────
EDGAR EFTS indexes filings submitted directly to EDGAR.gov. But ADV Part 2A
brochures are filed through IARD (FINRA's system) and published on IAPD — they
never touch EDGAR's full-text index. Confirmed via live test: zero hits for any
platform keyword. We skip Pass 1 entirely.

HOW PASS 2 WORKS (IAPD direct fetch)
──────────────────────────────────────
For each CRD in our rias table:
  1. Hit IAPD search API to get the current Part 2A brochure version ID
  2. Download the brochure PDF from files.adviserinfo.sec.gov
  3. Scan text for platform keywords
  4. Write matches to ria_platforms with source='adv_brochure'

Runs from local — no Railway IP needed. The IAPD search endpoint and brochure
file server have no IP restriction (unlike the firm detail /summary/{crd} endpoint).

Usage:
    make scan-brochures             # full scan
    make scan-brochures DRY=1       # dry run — print matches, no DB writes
    make scan-brochures V=1         # verbose — show each match as it's found
    python -m app.ingestion.brochure_scanner --probe 123456   # test one CRD
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

# Checked in order — longer/more-specific phrases first to avoid sub-match confusion.
# dict preserves insertion order (Python 3.7+).
PLATFORM_PHRASES: dict[str, str] = {
    "iCapital Network":  "iCapital",
    "icapitalnetwork":   "iCapital",
    "iCapital":          "iCapital",
    "CAIS Group":        "CAIS",
    "caisgroup.com":     "CAIS",
    "CAIS platform":     "CAIS",
    "CAIS":              "CAIS",
    "SEI Access":        "Altigo",   # Altigo rebranded → SEI Access in late 2023
    "Altigo":            "Altigo",
    "Halo Investing":    "Halo",
    "Halo platform":     "Halo",
    "InvestX":           "InvestX",
    "Artivest":          "Artivest",
}

# Firms whose own name IS a platform — skip (don't tag iCapital as an iCapital partner)
_PLATFORM_OWN_NAMES = {
    "icapital", "cais", "altigo", "sei access", "halo investing",
    "investx", "artivest",
}

# ── endpoints ─────────────────────────────────────────────────────────────────

_IAPD_SUMMARY = "https://www.adviserinfo.sec.gov/firm/summary"   # HTML page, has brochure link
_IAPD_FILES   = "https://files.adviserinfo.sec.gov/IAPD/Content/Common/crd_iapd_Brochure.aspx"

_IAPD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.adviserinfo.sec.gov/",
    "Origin":  "https://www.adviserinfo.sec.gov",
}

_CONCURRENCY = 5    # parallel brochure fetches — conservative for IAPD
_DELAY       = 0.2  # seconds between requests


# ── helpers ───────────────────────────────────────────────────────────────────

def _scan_text(text: str) -> list[str]:
    """Return list of canonical platform names found in text. Deduped, ordered."""
    found: list[str] = []
    lower = text.lower()
    for phrase, canonical in PLATFORM_PHRASES.items():
        if phrase.lower() in lower and canonical not in found:
            found.append(canonical)
    return found


def _is_platform_itself(firm_name: str) -> bool:
    lower = firm_name.lower()
    return any(own in lower for own in _PLATFORM_OWN_NAMES)


async def _load_all_crds() -> list[tuple[str, str]]:
    """
    Load ALL active RIAs from rias table. Paginates in chunks of 1,000
    to work around Supabase's default 1,000-row query limit.
    Returns list of (crd_number, firm_name).
    """
    db = get_db()
    results: list[tuple[str, str]] = []
    chunk = 1000
    start = 0

    while True:
        rows = (
            db.table("rias")
            .select("crd_number, firm_name")
            .eq("is_active", True)
            .range(start, start + chunk - 1)
            .execute()
        ).data or []

        for r in rows:
            crd = r.get("crd_number", "").strip()
            name = r.get("firm_name", "").strip()
            if crd:
                results.append((crd, name))

        if len(rows) < chunk:
            break   # last page
        start += chunk

    return results


# ── brochure fetch ────────────────────────────────────────────────────────────

async def _get_brochure_version_id(crd: str, client: httpx.AsyncClient) -> str | None:
    """
    Scrape the public IAPD firm summary HTML page to extract the Part 2A
    brochure version ID from the "Download Brochure" link href.

    URL: https://www.adviserinfo.sec.gov/firm/summary/{crd}
    This is a standard public page — no auth, no IP restriction.

    The page contains a link like:
      href=".../crd_iapd_Brochure.aspx?BRCHR_VRSN_ID=12345678"
    We regex-extract the BRCHR_VRSN_ID value and return it.
    """
    url = f"{_IAPD_SUMMARY}/{crd}"
    try:
        resp = await client.get(url, headers=_IAPD_HEADERS, timeout=12, follow_redirects=True)
        if resp.status_code != 200:
            return None
        await asyncio.sleep(_DELAY)
        html = resp.text
        # IAPD embeds brochure links as:
        #   BRCHR_VRSN_ID=12345678  (in href and in onclick attributes)
        match = re.search(r"BRCHR_VRSN_ID=(\d+)", html, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


async def _fetch_brochure_text(version_id: str, client: httpx.AsyncClient) -> str | None:
    """Download a Part 2A brochure PDF by version ID and extract its text."""
    try:
        resp = await client.get(
            _IAPD_FILES,
            headers=_IAPD_HEADERS,
            params={"BRCHR_VRSN_ID": version_id},
            timeout=25,
        )
        if resp.status_code != 200:
            return None
        pdf_bytes = resp.content
        if len(pdf_bytes) < 1000:   # not a real PDF — probably an error page
            return None

        def _extract(b: bytes) -> str:
            with pdfplumber.open(io.BytesIO(b)) as pdf:
                return "\n".join(
                    page.extract_text() or ""
                    for page in pdf.pages[:30]  # Part 2A rarely exceeds 30 pages
                )

        return await asyncio.to_thread(_extract, pdf_bytes)
    except Exception:
        return None


async def _scan_one(
    crd: str,
    firm_name: str,
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> tuple[str, list[str], str]:
    """
    Fetch and scan one RIA's Part 2A brochure.
    Returns (crd, [matched_platforms], status_reason).
    """
    if _is_platform_itself(firm_name):
        return crd, [], "skip:is_platform"

    async with sem:
        version_id = await _get_brochure_version_id(crd, client)
        if not version_id:
            return crd, [], "no_brochure_id"

        text = await _fetch_brochure_text(version_id, client)
        if not text:
            return crd, [], "pdf_fetch_failed"

        found = _scan_text(text)
        return crd, found, f"scanned:{len(text)}chars"


# ── probe mode ───────────────────────────────────────────────────────────────

async def probe(crd: str) -> None:
    """
    Test the full pipeline for a single CRD. Prints every step.
    Use this to verify the brochure fetch works before running on all RIAs.

    Usage:  python -m app.ingestion.brochure_scanner --probe 123456
    """
    print(f"\nProbing CRD {crd}...\n")
    async with httpx.AsyncClient() as client:
        # Show raw HTML around brochure links for debugging
        print(f"  Step 1: fetching IAPD firm summary page...")
        url = f"{_IAPD_SUMMARY}/{crd}"
        try:
            resp = await client.get(url, headers=_IAPD_HEADERS, timeout=12, follow_redirects=True)
            print(f"  HTTP {resp.status_code}  |  {len(resp.text):,} chars")
            # Show any BRCHR_VRSN_ID references in the page
            matches = re.findall(r".{0,60}BRCHR_VRSN_ID.{0,60}", resp.text, re.IGNORECASE)
            if matches:
                print(f"  Found {len(matches)} brochure version ID reference(s) in HTML:")
                for m in matches[:3]:
                    print(f"    {m.strip()}")
            else:
                print("  No BRCHR_VRSN_ID found in page HTML.")
                # Show a snippet to understand what the page looks like
                snippet = resp.text[:800].replace("\n", " ").replace("\r", "")
                print(f"\n  Page snippet (first 800 chars):\n  {snippet}\n")
        except Exception as exc:
            print(f"  ✗  Page fetch failed: {exc}")
            return

        print(f"\n  Step 2: extracting version ID...")
        vid = await _get_brochure_version_id(crd, client)
        if not vid:
            print("  ✗  No brochure version ID extracted.")
            print("     Possible reasons:")
            print("     - Firm is state-registered (no IAPD brochure on file)")
            print("     - Page structure has changed — check snippet above")
            print("     - CRD not found / redirected away")
            return

        print(f"  ✓  Brochure version ID: {vid}")
        print(f"\n  Step 2: downloading brochure PDF...")
        text = await _fetch_brochure_text(vid, client)
        if not text:
            print("  ✗  PDF download or parse failed.")
            return

        print(f"  ✓  Extracted {len(text):,} characters from PDF")
        print(f"\n  Step 3: scanning for platform keywords...")
        found = _scan_text(text)
        if found:
            print(f"  ✓  PLATFORMS FOUND: {found}")
        else:
            print("  —  No platform keywords found in this brochure.")

        # Show a snippet of text around any matches for verification
        for phrase in PLATFORM_PHRASES:
            idx = text.lower().find(phrase.lower())
            if idx != -1:
                snippet = text[max(0, idx-80):idx+120].replace("\n", " ")
                print(f'\n  Context for "{phrase}":\n    "...{snippet}..."')


# ── main scan ────────────────────────────────────────────────────────────────

async def run(dry_run: bool = False, verbose: bool = False) -> None:
    print(f"\npcIQ ADV brochure scanner  |  dry_run={dry_run}")

    all_rias = await _load_all_crds()
    print(f"  {len(all_rias):,} active RIAs loaded from DB (paginated)\n")

    sem = asyncio.Semaphore(_CONCURRENCY)
    matched: dict[str, list[str]] = defaultdict(list)
    total  = len(all_rias)
    done   = 0
    hits   = 0
    no_id  = 0
    start  = time.monotonic()

    # Single shared client for the whole run — reuses connections
    async with httpx.AsyncClient() as client:

        async def _staggered(crd: str, name: str, i: int):
            await asyncio.sleep(i * 0.05)
            return await _scan_one(crd, name, sem, client)

        tasks = [
            asyncio.create_task(_staggered(crd, name, i))
            for i, (crd, name) in enumerate(all_rias)
        ]

        for fut in asyncio.as_completed(tasks):
            crd, platforms, reason = await fut
            done += 1
            if reason == "no_brochure_id":
                no_id += 1
            if platforms:
                hits += 1
                matched[crd] = platforms
                if verbose:
                    print(f"\n  ✓  CRD {crd} → {', '.join(platforms)}")

            elapsed = time.monotonic() - start
            rate    = done / elapsed if elapsed > 0 else 1
            eta_s   = (total - done) / rate if rate > 0 else 0
            bar     = "█" * int(30 * done / total) + "░" * (30 - int(30 * done / total))
            print(
                f"  [{bar}] {done/total*100:4.0f}%  "
                f"{hits} matches  {no_id} no-brochure  "
                f"eta {eta_s/60:.0f}m",
                end="\r", flush=True,
            )

    elapsed = time.monotonic() - start
    print(f"\n\n{'─'*60}")
    print(f"  Completed in {elapsed/60:.1f} min")
    print(f"  RIAs scanned:     {total:,}")
    print(f"  With brochure:    {total - no_id:,}")
    print(f"  Platform matches: {hits:,}")
    print(f"  No IAPD brochure: {no_id:,} (state-registered or exempt — expected)")

    if matched:
        print(f"\n  Matches by platform:")
        counts: dict[str, int] = defaultdict(int)
        for platforms in matched.values():
            for p in platforms:
                counts[p] += 1
        for p, n in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {p}: {n}")

    if not dry_run and matched:
        print(f"\n  Writing {sum(len(v) for v in matched.values())} rows to ria_platforms...")
        written = 0
        for crd, platforms in matched.items():
            for platform in platforms:
                try:
                    upsert_ria_platform(crd, platform, source="adv_brochure")
                    written += 1
                except Exception as exc:
                    if verbose:
                        print(f"  ✗  DB write {crd}/{platform}: {exc}")
        print(f"  ✓  {written} rows written (source='adv_brochure')")
        print(f"  These appear in FundModal Confirmed Allocators.")
    elif dry_run and matched:
        print(f"\n  Dry run — no DB writes. Re-run without DRY=1 to persist.")

    print()


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="pcIQ — ADV Part 2A brochure platform scanner"
    )
    parser.add_argument(
        "--probe", metavar="CRD",
        help="Test the full pipeline for a single CRD number and exit"
    )
    parser.add_argument("--dry-run",  action="store_true", help="No DB writes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each match")
    # Legacy flags kept for Makefile compatibility — ignored now that Pass 1 is removed
    parser.add_argument("--pass1-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pass2-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.probe:
        asyncio.run(probe(args.probe))
    else:
        asyncio.run(run(dry_run=args.dry_run, verbose=args.verbose))


if __name__ == "__main__":
    main()
