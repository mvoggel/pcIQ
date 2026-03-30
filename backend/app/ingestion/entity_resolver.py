"""
Entity resolution for fund and firm names.

The problem: EDGAR filings use inconsistent legal names.
  "Blue Owl Capital LLC"
  "Blue Owl Capital Inc."
  "Blue Owl Capital Fund III, L.P."
  "Blue Owl Capital Fund III (Parallel), L.P."

These should all resolve to a canonical entity: "Blue Owl Capital"

Phase 1 approach: rule-based normalization → canonical key → in-memory dedup.
Phase 2: persist to entities table, add fuzzy matching for edge cases.
"""

import re

# Legal suffixes to strip when building canonical keys
_LEGAL_SUFFIXES = re.compile(
    r"""\b(
        llc | l\.l\.c\. | l\.p\. | lp | ltd | limited |
        inc | incorporated | corp | corporation |
        gp | general\s+partner | co-investment |
        trust | n\.a\. | plc
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Fund series/numbering patterns to strip
_SERIES_PATTERNS = re.compile(
    r"""\b(
        fund\s+[ivxlcdm]+       |   # Fund I, Fund II, Fund III, Fund IV...
        fund\s+\d+              |   # Fund 2, Fund 3
        series\s+[a-z\d]+       |   # Series A, Series 1
        vintage\s+\d{4}         |   # Vintage 2024
        \d{4}\s+vintage         |   # 2024 Vintage
        parallel                |   # (Parallel)
        feeder                  |   # (Feeder)
        offshore                |   # (Offshore)
        onshore                 |   # (Onshore)
        co\-invest              |   # Co-Invest
        co\s+invest             |
        side\s+car              |   # Side Car
        sidecar                 |
        qfpf                    |   # QFPF (qualified foreign pension fund)
        special\s+feeder        |
        \(.*?\)                     # anything in parentheses
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Punctuation/extra whitespace cleanup
_PUNCT = re.compile(r"[,\.\-/\\]+")
_WHITESPACE = re.compile(r"\s{2,}")


def canonical_key(name: str) -> str:
    """
    Reduce a fund name to a normalized key for entity matching.

    Examples:
        "Blue Owl Capital Fund III, L.P."         → "blue owl capital"
        "Blue Owl Capital (Offshore) II, L.P."    → "blue owl capital"
        "Greystar Global Strategic Partners II"   → "greystar global strategic partners"
    """
    s = name.strip()
    s = _SERIES_PATTERNS.sub(" ", s)
    s = _LEGAL_SUFFIXES.sub(" ", s)
    s = _PUNCT.sub(" ", s)
    s = _WHITESPACE.sub(" ", s)
    return s.lower().strip()


class EntityResolver:
    """
    In-memory entity resolution for a single ingestion run.

    Builds a map of canonical_key → entity_id as filings are processed.
    Entities that share a canonical key are considered the same firm.

    Phase 2: this logic moves to the DB (entities table + fuzzy index).
    """

    def __init__(self) -> None:
        # canonical_key → {"id": int, "canonical_name": str, "cik": str}
        self._entities: dict[str, dict] = {}
        self._next_id = 1

    def resolve(self, name: str, cik: str = "") -> dict:
        """
        Resolve a fund name to an entity record, creating one if new.

        Returns a dict with keys: id, canonical_name, cik, is_new
        """
        key = canonical_key(name)
        if not key:
            key = name.lower().strip()

        if key in self._entities:
            entity = self._entities[key]
            # Update CIK if we now have one and didn't before
            if cik and not entity["cik"]:
                entity["cik"] = cik
            return {**entity, "is_new": False}

        entity = {
            "id": self._next_id,
            "canonical_name": _to_title(key),
            "cik": cik,
        }
        self._entities[key] = entity
        self._next_id += 1
        return {**entity, "is_new": True}

    @property
    def all_entities(self) -> list[dict]:
        return list(self._entities.values())


def _to_title(key: str) -> str:
    """Convert a lowercase canonical key back to title case."""
    return " ".join(w.capitalize() for w in key.split())
