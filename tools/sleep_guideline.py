"""
tools/sleep_guidelines.py — RestIQ Sleep Concierge Agent

Age-based recommended sleep duration lookup.

Source: Centers for Disease Control and Prevention (CDC), "About Sleep"
(https://www.cdc.gov/sleep/about/index.html), reflecting the joint consensus
statement of the American Academy of Sleep Medicine (AASM) and the Sleep
Research Society (Watson NF, Badr MS, Belenky G, et al. "Recommended Amount
of Sleep for a Healthy Adult." Sleep. 2015;38(6):843-844), and the AASM
pediatric consensus (Paruthi S, et al. J Clin Sleep Med. 2016;12:1549-61).

This module is intentionally passive: importing it does no work, hits no
database, and calls no LLM. It only executes when a caller (Intake Agent
or Analyzer Agent) explicitly invokes get_recommended_hours() or
evaluate_duration_against_guideline() for a specific user/age. Nothing
here runs automatically or on a schedule.
"""

from __future__ import annotations

import logging
import math
from typing import Any, NamedTuple

from schemas import VerdictLabel

logger = logging.getLogger("tools.sleep_guidelines")


class SleepGuideline(NamedTuple):
    label: str
    min_hours: float
    max_hours: float


# CDC / AASM / Sleep Research Society consensus, ordered by lower age bound.
# Intervals are half-open [lower, upper) for every bucket except the final
# one, which is open-ended (65+). A caller with age_years == 18.0 therefore
# falls into the Adult bucket, not Teen — numeric bounds are aligned with
# each label's own stated range (Teen "13-18" ends just before 18; Adult
# "18-64" begins at 18), so there is no overlap and no gap.
_GUIDELINE_TABLE: list[tuple[float, float, SleepGuideline]] = [
    (0, 0.25, SleepGuideline("Newborn (0-3 months)", 14, 17)),
    (0.25, 1, SleepGuideline("Infant (4-12 months)", 12, 16)),
    (1, 3, SleepGuideline("Toddler (1-2 years)", 11, 14)),
    (3, 6, SleepGuideline("Preschool (3-5 years)", 10, 13)),
    (6, 13, SleepGuideline("School age (6-12 years)", 9, 12)),
    (13, 18, SleepGuideline("Teen (13-18 years)", 8, 10)),
    (18, 65, SleepGuideline("Adult (18-64 years)", 7, 9)),
    (65, math.inf, SleepGuideline("Older adult (65+ years)", 7, 8)),
]

SOURCE_CITATION = (
    "CDC (cdc.gov/sleep) / AASM & Sleep Research Society consensus "
    "(Watson et al., Sleep 2015; Paruthi et al., J Clin Sleep Med 2016)"
)

# URL fetched only by the opt-in fetch_source_verification() below — never
# touched automatically on import or during a normal lookup call.
_SOURCE_URL = "https://www.cdc.gov/sleep/about/index.html"
_verification_cache: dict[str, Any] | None = None


def get_recommended_hours(age_years: float) -> SleepGuideline:
    """Return the CDC/AASM-recommended sleep range for a given age.

    Called on-demand by Intake (to sanity-check a logged duration against
    what's biologically expected for the user) or by Analyzer (to compare
    a rolling average against the user's age-appropriate target). Not
    invoked automatically for every check-in — only when the caller has
    an age on hand and needs the benchmark.
    """
    if age_years < 0:
        raise ValueError("age_years must be non-negative.")

    for lower, upper, guideline in _GUIDELINE_TABLE:
        if lower <= age_years < upper:
            logger.debug(
                "[SLEEP_GUIDELINES] age=%s -> %s (%s-%s hrs)",
                age_years, guideline.label, guideline.min_hours, guideline.max_hours,
            )
            return guideline

    # Age at or above the top of the table falls into the final band.
    return _GUIDELINE_TABLE[-1][2]


def evaluate_duration_against_guideline(
    age_years: float, average_duration_hours: float
) -> dict[str, Any]:
    """Compare a measured average sleep duration against the age-appropriate range.

    Returns a small dict (not a DB write, not a schema mutation) so Analyzer
    can fold the result into its existing patterns_detected / recommendations
    lists without needing changes to schemas.py or the DB layer.

    "verdict" is a VerdictLabel member (ON_TRACK / NEEDS_ATTENTION /
    IMPROVING) reused from schemas.py for consistency with the rest of the
    analysis pipeline. If this dict is ever serialized to JSON, convert it
    with verdict.value first — VerdictLabel is not JSON-serializable as-is.
    """
    if average_duration_hours < 0:
        raise ValueError("average_duration_hours must be non-negative.")

    guideline = get_recommended_hours(age_years)
    within_range = guideline.min_hours <= average_duration_hours <= guideline.max_hours

    if within_range:
        verdict = VerdictLabel.ON_TRACK
        note = (
            f"Average of {average_duration_hours:.1f}h/night is within the "
            f"{guideline.min_hours}-{guideline.max_hours}h range recommended for "
            f"{guideline.label.lower()}."
        )
    elif average_duration_hours < guideline.min_hours:
        verdict = VerdictLabel.NEEDS_ATTENTION
        deficit = guideline.min_hours - average_duration_hours
        note = (
            f"Average of {average_duration_hours:.1f}h/night is {deficit:.1f}h below the "
            f"{guideline.min_hours}-{guideline.max_hours}h range recommended for "
            f"{guideline.label.lower()}."
        )
    else:
        verdict = VerdictLabel.IMPROVING
        surplus = average_duration_hours - guideline.max_hours
        note = (
            f"Average of {average_duration_hours:.1f}h/night is {surplus:.1f}h above the "
            f"{guideline.min_hours}-{guideline.max_hours}h range recommended for "
            f"{guideline.label.lower()}."
        )

    return {
        "age_band": guideline.label,
        "recommended_min_hours": guideline.min_hours,
        "recommended_max_hours": guideline.max_hours,
        "within_range": within_range,
        "verdict": verdict,
        "note": note,
        "source": SOURCE_CITATION,
    }


def fetch_source_verification(force_refresh: bool = False) -> dict[str, Any]:
    """Opt-in runtime check that the CDC source page is still reachable.

    This is the ONLY function in this module that touches the network, and
    it only runs when a caller explicitly invokes it — never on import,
    never as a side effect of get_recommended_hours() or
    evaluate_duration_against_guideline(). Useful for an admin/health-check
    path, not for the normal Intake/Analyzer call flow.

    Result is cached in-process after the first successful call; pass
    force_refresh=True to bypass the cache. Raises on network failure —
    callers should catch and fall back to the static SOURCE_CITATION string
    rather than letting a normal lookup fail because CDC's site is down.
    """
    global _verification_cache

    if _verification_cache is not None and not force_refresh:
        return _verification_cache

    import urllib.request

    logger.info("[SLEEP_GUIDELINES] fetch_source_verification -> %s", _SOURCE_URL)
    request = urllib.request.Request(_SOURCE_URL, headers={"User-Agent": "RestIQ/1.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        status = response.status
        reachable = status == 200

    _verification_cache = {
        "url": _SOURCE_URL,
        "reachable": reachable,
        "status_code": status,
    }
    return _verification_cache