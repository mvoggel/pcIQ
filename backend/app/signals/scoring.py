"""
Territory signal scoring engine.

Takes parsed Form D filings and produces actionable intelligence:
  - Which states have the most private credit activity this week?
  - Which platforms are most active in a given territory?
  - Which new fund raises should a wholesaler in state X care about?

Phase 1: pure Python, runs over in-memory filing list.
Phase 2: moves to DB queries + scheduled jobs.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.models.form_d import FormDFiling


@dataclass
class TerritorySignal:
    """A single actionable signal for a wholesaler's territory."""
    fund_name: str
    fund_type: str
    offering_size_m: float | None
    date_of_first_sale: date | None
    fund_state: str                          # where the fund is based
    platforms: list[str]                     # distribution platforms
    known_platforms: list[str]               # iCapital, CAIS, etc.
    solicitation_states: list[str]           # states being targeted
    is_in_territory: bool = False
    priority_score: float = 0.0              # 0.0–10.0


@dataclass
class TerritoryReport:
    """Aggregated signal report for one territory (set of states)."""
    territory_name: str
    states: list[str]
    signals: list[TerritorySignal] = field(default_factory=list)
    platform_counts: dict[str, int] = field(default_factory=dict)
    total_filings_scanned: int = 0

    @property
    def top_signals(self) -> list[TerritorySignal]:
        return sorted(self.signals, key=lambda s: s.priority_score, reverse=True)

    @property
    def known_platform_activity(self) -> dict[str, int]:
        return {k: v for k, v in self.platform_counts.items()
                if any(p in k.lower() for p in ["icapital", "cais", "altigo", "moonfare"])}


def score_filing(filing: FormDFiling, territory_states: set[str]) -> TerritorySignal:
    """
    Score a single filing for relevance to a territory.

    Priority score logic (0–10):
      +3  known platform (iCapital, CAIS) is distributing
      +2  solicitation states overlap with territory
      +2  offering size > $50M
      +1  offering size > $10M
      +1  date_of_first_sale within last 14 days (fresh signal)
      +1  Private Equity Fund type (most relevant to private credit)
    """
    score = 0.0

    # Known platform bonus
    if filing.known_platform_names:
        score += 3.0

    # Territory overlap — states being solicited overlap with wholesaler territory
    sol_states = filing.all_solicitation_states
    if sol_states == {"ALL"}:
        score += 2.0
        in_territory = True
    else:
        overlap = sol_states & territory_states
        if overlap:
            score += 2.0
        in_territory = bool(overlap) or filing.address.state_or_country.upper() in territory_states

    # Size bonus
    size = filing.offering_size_m or 0
    if size > 50:
        score += 2.0
    elif size > 10:
        score += 1.0

    # Freshness bonus (within 14 days)
    if filing.date_of_first_sale:
        days_old = (date.today() - filing.date_of_first_sale).days
        if days_old <= 14:
            score += 1.0

    # Fund type bonus
    if "private equity" in filing.investment_fund_type.lower():
        score += 1.0

    return TerritorySignal(
        fund_name=filing.entity_name,
        fund_type=filing.investment_fund_type,
        offering_size_m=filing.offering_size_m,
        date_of_first_sale=filing.date_of_first_sale,
        fund_state=filing.address.state_or_country.upper(),
        platforms=filing.platform_names,
        known_platforms=filing.known_platform_names,
        solicitation_states=sorted(sol_states - {"ALL"}),
        is_in_territory=in_territory,
        priority_score=round(min(score, 10.0), 1),
    )


def generate_territory_report(
    filings: list[FormDFiling],
    territory_name: str,
    territory_states: list[str],
) -> TerritoryReport:
    """
    Generate a territory intelligence report from a list of filings.

    Args:
        filings:          List of private-credit-candidate FormDFiling objects
        territory_name:   Display name (e.g. "Southwest", "New York Metro")
        territory_states: 2-letter state codes (e.g. ["AZ", "NV", "UT"])
    """
    states_set = {s.upper() for s in territory_states}
    report = TerritoryReport(
        territory_name=territory_name,
        states=territory_states,
        total_filings_scanned=len(filings),
    )

    platform_counts: dict[str, int] = defaultdict(int)

    for filing in filings:
        signal = score_filing(filing, states_set)
        report.signals.append(signal)

        # Count platform activity across all filings (not just territory)
        for p in filing.platform_names:
            platform_counts[p] += 1

    report.platform_counts = dict(platform_counts)
    return report


def print_territory_report(report: TerritoryReport) -> None:
    """Print a formatted territory signal report to stdout."""
    divider = "─" * 80
    print(f"\n{'═'*80}")
    print(f"  TERRITORY SIGNAL REPORT — {report.territory_name}")
    print(f"  States: {', '.join(report.states)}")
    print(f"{'═'*80}\n")

    # Platform activity summary
    if report.platform_counts:
        print("  PLATFORM ACTIVITY (all filings this period):")
        for name, count in sorted(report.platform_counts.items(), key=lambda x: -x[1])[:8]:
            flag = " ★" if any(p in name.lower() for p in ["icapital", "cais", "altigo"]) else ""
            print(f"    {name:45s}  {count:3d} fund(s){flag}")
        print()

    # Top signals in territory
    in_territory = [s for s in report.top_signals if s.is_in_territory]
    if in_territory:
        print(f"  TOP SIGNALS IN TERRITORY ({len(in_territory)} funds):")
        print(f"  {'Score':>5}  {'Fund':52s}  {'Size':>10}  {'Platforms'}")
        print(f"  {divider}")
        for sig in in_territory[:15]:
            size = f"${sig.offering_size_m}M" if sig.offering_size_m else "unknown"
            platforms = ", ".join(sig.known_platforms or sig.platforms[:2]) or "—"
            print(f"  {sig.priority_score:>5.1f}  {sig.fund_name:52s}  {size:>10}  {platforms}")
    else:
        print("  No signals matched this territory in this period.")

    print(f"\n  Scanned {report.total_filings_scanned} filings total.")
    print(f"{'═'*80}\n")
