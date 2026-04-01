"""
ADV Part 1A PDF parser.

Downloads and parses the Form ADV PDF from the SEC's report server.
URL pattern (no auth required):
  https://reports.adviserinfo.sec.gov/reports/ADV/{crd}/PDF/{crd}.pdf

Extracts from Item 5 (Information About Your Advisory Business):
  - Total regulatory AUM  (Item 5.F — discretionary + non-discretionary)
  - Discretionary AUM     (Item 5.F)
  - Total client count    (Item 5.F)
  - Employee count        (Item 5.A)
  - Investment advisory employees  (Item 5.B.1)
  - Client type breakdown (Item 5.D — pooled vehicles, HNW, institutions, etc.)

The form is standardized across all SEC-registered advisers (Rev. 10/2021),
so field labels and table positions are consistent.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass, field

import httpx
import pdfplumber

ADV_PDF_BASE = "https://reports.adviserinfo.sec.gov/reports/ADV"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pcIQ-research/1.0)"}

# Client type labels matching Item 5.D lettering in the form
_CLIENT_TYPE_MAP = {
    "a": "Individuals",
    "b": "High Net Worth Individuals",
    "c": "Banking / Thrift",
    "d": "Investment Companies",
    "e": "Business Development Companies",
    "f": "Pooled Investment Vehicles",
    "g": "Pension / Profit Sharing Plans",
    "h": "Charitable Organizations",
    "i": "State / Municipal Government",
    "j": "Other Investment Advisers",
    "k": "Insurance Companies",
    "l": "Sovereign Wealth Funds",
    "m": "Corporations / Other Businesses",
    "n": "Other",
}


@dataclass
class ADVData:
    crd: str
    firm_name: str = ""
    # AUM
    total_aum: float | None = None
    discretionary_aum: float | None = None
    non_discretionary_aum: float | None = None
    # Counts
    total_clients: int | None = None
    total_employees: int | None = None
    investment_advisory_employees: int | None = None
    # Client type breakdown {label: {"clients": int|None, "aum": float|None}}
    client_types: dict[str, dict] = field(default_factory=dict)
    # Source
    pdf_url: str = ""


def _clean(text: str) -> str:
    """Collapse repeated whitespace and strip control chars."""
    return re.sub(r"\s+", " ", text).strip()


def _to_float(s: str) -> float | None:
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> int | None:
    s = s.replace(",", "").strip()
    try:
        return int(s)
    except ValueError:
        return None


_ADV_MAX_PAGES = 35  # Items 5.A/B/D/F always appear in the first section of Part 1A


def _extract_all_text(pdf_bytes: bytes) -> str:
    """Extract text from the first _ADV_MAX_PAGES pages.

    Form ADV Part 1A is standardised — Items 5.A, 5.B, 5.D, and 5.F
    (employees, client types, AUM) always fall within the first ~25 pages.
    Parsing the full document for a large manager (200+ pages) was taking
    30-45 s; capping at 35 pages keeps it under 2 s.
    """
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        pages = pdf.pages[:_ADV_MAX_PAGES]
        return "\n".join(page.extract_text() or "" for page in pages)


def _parse_item5_aum(text: str) -> tuple[float | None, float | None, float | None, int | None]:
    """
    Parse Item 5.F AUM table.

    Form format (standardized):
      Discretionary: (a) $ 5,504,310,620 (d) 14
      Non-Discretionary: (b) $ 0 (e) 0
      Total: (c) $ 5,504,310,620 (f) 14

    Returns (discretionary_aum, non_disc_aum, total_aum, total_clients).
    """
    # Match the full three-row table
    pat = re.compile(
        r"Discretionary:\s*\(a\)\s*\$\s*([\d,]+)\s*\(d\)\s*(\d+)"
        r".*?Non-Discretionary:\s*\(b\)\s*\$\s*([\d,]+)\s*\(e\)\s*(\d+)"
        r".*?Total:\s*\(c\)\s*\$\s*([\d,]+)\s*\(f\)\s*(\d+)",
        re.S,
    )
    m = pat.search(text)
    if not m:
        return (None, None, None, None)

    disc_aum   = _to_float(m.group(1))
    disc_cnt   = _to_int(m.group(2))
    non_disc   = _to_float(m.group(3))
    # non_disc_cnt = _to_int(m.group(4))   # not surfaced
    total_aum  = _to_float(m.group(5))
    total_cnt  = _to_int(m.group(6))

    return (disc_aum, non_disc, total_aum, total_cnt)


def _parse_item5_employees(text: str) -> tuple[int | None, int | None]:
    """
    Parse Item 5.A (total employees) and 5.B.(1) (investment advisory).

    Form format:
      A. Approximately how many employees do you have? ...
      53
      B. (1) Approximately how many of the employees ... perform investment advisory functions ...
      45
    """
    total_emp = None
    advisory_emp = None

    m_a = re.search(
        r"A\.\s+Approximately how many employees.*?(\d+)\s*\n"
        r".*?B\.\s*\(1\).*?investment advisory.*?(\d+)",
        text, re.S | re.I,
    )
    if m_a:
        total_emp   = _to_int(m_a.group(1))
        advisory_emp = _to_int(m_a.group(2))

    return (total_emp, advisory_emp)


def _parse_client_types(text: str) -> dict[str, dict]:
    """
    Parse Item 5.D client type table.

    The form has rows like:
      (a) Individuals (other than high net worth individuals) $
      (f) Pooled investment vehicles (other than investment companies and 6 $ 4,954,310,620
      (k) Insurance companies 8 $ 550,000,000

    Count and AUM (when non-zero) appear ON THE SAME LINE as the row's
    opening '(letter)'.  We scan line by line for lines starting with a
    letter code and extract values from that line only.
    """
    result: dict[str, dict] = {}

    # Narrow to the table section
    start = text.find("Indicate the approximate number of your clients")
    if start == -1:
        return result
    end_match = re.search(r"Compensation Arrangements", text[start:])
    table_text = text[start: start + end_match.start()] if end_match else text[start: start + 5000]

    # Process line by line — each row entry starts with \([a-n]\)
    row_line_pat = re.compile(
        r"^\s*\(([a-n])\)\s+"      # letter code at line start
        r"(.*?)"                   # description (greedily to end of line)
        r"(?:(\d[\d,]*)\s+)?"     # optional: client count before $
        r"\$\s*([\d,]+)?"         # optional: AUM after $
        r"\s*$",                   # end of line
        re.MULTILINE,
    )

    for m in row_line_pat.finditer(table_text):
        letter     = m.group(1)
        label      = _CLIENT_TYPE_MAP.get(letter, letter)
        count_str  = (m.group(3) or "").strip()
        amount_str = (m.group(4) or "").strip()

        count  = _to_int(count_str)   if count_str  else None
        amount = _to_float(amount_str) if amount_str else None

        if count is not None or amount is not None:
            result[label] = {"clients": count, "aum": amount}

    return result


def parse_adv_pdf(crd: str, pdf_bytes: bytes) -> ADVData:
    """Parse raw PDF bytes into an ADVData record."""
    text = _extract_all_text(pdf_bytes)

    # Firm name from header
    m_name = re.search(r"Primary Business Name:\s*(.+?)\s+CRD Number:", text)
    firm_name = m_name.group(1).strip().title() if m_name else ""

    disc_aum, non_disc, total_aum, total_clients = _parse_item5_aum(text)
    total_emp, advisory_emp = _parse_item5_employees(text)
    client_types = _parse_client_types(text)

    pdf_url = f"{ADV_PDF_BASE}/{crd}/PDF/{crd}.pdf"

    return ADVData(
        crd=crd,
        firm_name=firm_name,
        total_aum=total_aum,
        discretionary_aum=disc_aum,
        non_discretionary_aum=non_disc,
        total_clients=total_clients,
        total_employees=total_emp,
        investment_advisory_employees=advisory_emp,
        client_types=client_types,
        pdf_url=pdf_url,
    )


async def fetch_adv_data(crd: str, timeout: float = 12.0) -> ADVData | None:
    """
    Download and parse the ADV PDF for a given CRD number.
    Returns None on any error (404, timeout, parse failure).
    """
    if not crd:
        return None

    _MAX_PDF_BYTES = 8 * 1024 * 1024  # 8 MB — large-firm PDFs (Macquarie etc.) OOM Railway

    url = f"{ADV_PDF_BASE}/{crd}/PDF/{crd}.pdf"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # HEAD first: skip giant PDFs before downloading
            head = await client.head(url, headers=_HEADERS)
            content_length = int(head.headers.get("content-length", 0))
            if content_length > _MAX_PDF_BYTES:
                return None

            resp = await client.get(url, headers=_HEADERS)
            if resp.status_code != 200:
                return None
            if len(resp.content) > _MAX_PDF_BYTES:
                return None  # guard: server didn't send Content-Length but PDF is still large

            return await asyncio.to_thread(parse_adv_pdf, crd, resp.content)
    except Exception:
        return None
