"""
plan_engine.py — RestIQ Adaptive Plan Engine
Pure decision logic for evaluating and adjusting a user's sleep plan.

Deliberately kept separate from mcp_server.py: this module owns the
*business logic* of "should the plan change, and to what" while
mcp_server.py only owns the thin MCP tool wrapper around it (DB I/O,
request/response shape). Keeping these apart means the decision rules
can be unit-tested or reused without spinning up the MCP transport layer.

Evaluation order (all three rules run; first applicable one wins):
  1. STREAK_OVERRIDE   — 3+ consecutive nights below a low-score threshold
                          triggers an immediate adjustment, any day of the week.
  2. ROLLING_TREND      — 7-day rolling average vs. the previous 7-day window,
                          computed every check-in but only used to decide
                          IMPROVING/DECLINING/STABLE status.
  3. WEEKLY_COMPARISON  — the same rolling-trend comparison, but this is the
                          one that actually *commits* a target-bedtime change,
                          gated to fire once per week (called from the weekly
                          report flow rather than every daily check-in).
"""

import logging
import datetime
from datetime import date, timedelta
from typing import Optional

from schemas import PlanStatus, PlanTrigger, PlanAdjustmentSchema

logger = logging.getLogger("plan_engine")

# ──────────────────────────────────────────────────────────────────────────────
# Tunable thresholds
# ──────────────────────────────────────────────────────────────────────────────

STREAK_LOW_SCORE_THRESHOLD = 50   # a night below this counts as "bad"
STREAK_LENGTH_TRIGGER = 3         # this many bad nights in a row triggers override
TREND_DELTA_THRESHOLD = 5.0       # min point-difference to call it improving/declining
BEDTIME_SHIFT_MINUTES = 15        # how much to nudge target bedtime per adjustment
MIN_ENTRIES_FOR_TREND = 4         # need at least this many nights to trust a trend


def _shift_time(hhmm: str, minutes: int) -> str:
    """Shifts a HH:MM time string by +/- minutes, wrapping around midnight."""
    h, m = map(int, hhmm.split(":"))
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _check_streak_override(scores_recent_first: list[int]) -> bool:
    """
    Checks if the most recent N nights (recent-first order) are all below
    the low-score threshold. Returns True if the streak override should fire.
    """
    if len(scores_recent_first) < STREAK_LENGTH_TRIGGER:
        return False
    recent_window = scores_recent_first[:STREAK_LENGTH_TRIGGER]
    return all(s < STREAK_LOW_SCORE_THRESHOLD for s in recent_window)


def _compute_rolling_trend(scores_recent_first: list[int]) -> tuple[Optional[float], Optional[float], PlanStatus]:
    """
    Splits the available scores (recent-first) into this-week vs last-week
    windows of up to 7 entries each, and classifies the trend.
    Returns (rolling_avg, previous_week_avg, status).
    """
    if len(scores_recent_first) < MIN_ENTRIES_FOR_TREND:
        return None, None, PlanStatus.INSUFFICIENT_DATA

    current_window = scores_recent_first[:7]
    previous_window = scores_recent_first[7:14]

    rolling_avg = sum(current_window) / len(current_window)

    if not previous_window:
        # Not enough history yet to compare weeks; we know the current
        # average but can't classify a direction with confidence.
        return round(rolling_avg, 1), None, PlanStatus.INSUFFICIENT_DATA

    previous_avg = sum(previous_window) / len(previous_window)
    delta = rolling_avg - previous_avg

    if delta >= TREND_DELTA_THRESHOLD:
        status = PlanStatus.IMPROVING
    elif delta <= -TREND_DELTA_THRESHOLD:
        status = PlanStatus.DECLINING
    else:
        status = PlanStatus.STABLE

    return round(rolling_avg, 1), round(previous_avg, 1), status


def evaluate_plan(
    user_id: str,
    scores_recent_first: list[int],
    current_target_bedtime: str,
    commit_weekly_adjustment: bool,
) -> PlanAdjustmentSchema:
    """
    Evaluates a user's sleep plan against their recent score history and
    decides whether the target bedtime should change.

    Args:
        user_id: the user being evaluated.
        scores_recent_first: sleep scores ordered most-recent-first (i.e.
            scores_recent_first[0] is last night's score).
        current_target_bedtime: the bedtime currently stored in the user's plan.
        commit_weekly_adjustment: when True (the weekly-report path), a
            DECLINING/IMPROVING rolling trend is allowed to actually change
            the stored target. When False (the daily check-in path), only
            the streak override is allowed to commit a change — the trend
            is still computed and returned for status purposes, but does not
            shift the bedtime, so users don't get nudged every single day.

    Returns:
        PlanAdjustmentSchema describing the decision and the reasoning.
    """
    logger.info(
        "[PLAN_ENGINE] Evaluating plan for user_id '%s' with %d scored nights (weekly_commit=%s)",
        user_id, len(scores_recent_first), commit_weekly_adjustment
    )

    # Rule 1: streak override — checked first, can fire any day.
    if _check_streak_override(scores_recent_first):
        new_bedtime = _shift_time(current_target_bedtime, -BEDTIME_SHIFT_MINUTES)
        reason = (
            f"Your last {STREAK_LENGTH_TRIGGER} nights all scored below "
            f"{STREAK_LOW_SCORE_THRESHOLD}/100, so I'm moving your target bedtime "
            f"{BEDTIME_SHIFT_MINUTES} minutes earlier to {new_bedtime} to help you catch up on rest."
        )
        logger.info("[PLAN_ENGINE] STREAK_OVERRIDE fired for user_id '%s': %s", user_id, reason)
        return PlanAdjustmentSchema(
            user_id=user_id,
            status=PlanStatus.DECLINING,
            triggered_by=PlanTrigger.STREAK_OVERRIDE,
            adjusted=True,
            previous_target_bedtime=current_target_bedtime,
            new_target_bedtime=new_bedtime,
            rolling_avg_score=None,
            previous_week_avg_score=None,
            reason=reason,
        )

    # Rules 2 & 3 share the same trend computation; they differ only in
    # whether the result is allowed to commit a change.
    rolling_avg, previous_avg, status = _compute_rolling_trend(scores_recent_first)

    if status == PlanStatus.INSUFFICIENT_DATA:
        reason = "Not enough check-ins yet to evaluate your plan. Keep logging daily and I'll start tracking trends."
        return PlanAdjustmentSchema(
            user_id=user_id,
            status=status,
            triggered_by=PlanTrigger.NONE,
            adjusted=False,
            previous_target_bedtime=current_target_bedtime,
            new_target_bedtime=current_target_bedtime,
            rolling_avg_score=rolling_avg,
            previous_week_avg_score=previous_avg,
            reason=reason,
        )

    if not commit_weekly_adjustment:
        # Daily check-in path: report the trend, but don't move the target.
        reason = f"Your rolling average is currently {rolling_avg}/100 ({status.value.lower()})."
        return PlanAdjustmentSchema(
            user_id=user_id,
            status=status,
            triggered_by=PlanTrigger.ROLLING_TREND,
            adjusted=False,
            previous_target_bedtime=current_target_bedtime,
            new_target_bedtime=current_target_bedtime,
            rolling_avg_score=rolling_avg,
            previous_week_avg_score=previous_avg,
            reason=reason,
        )

    # Weekly path: a confirmed trend is allowed to commit a bedtime shift.
    if status == PlanStatus.DECLINING:
        new_bedtime = _shift_time(current_target_bedtime, -BEDTIME_SHIFT_MINUTES)
        reason = (
            f"Your average score dropped from {previous_avg} to {rolling_avg} this week, "
            f"so I'm moving your target bedtime {BEDTIME_SHIFT_MINUTES} minutes earlier to {new_bedtime}."
        )
        adjusted = True
    elif status == PlanStatus.IMPROVING:
        new_bedtime = _shift_time(current_target_bedtime, BEDTIME_SHIFT_MINUTES)
        reason = (
            f"Great progress — your average score rose from {previous_avg} to {rolling_avg} this week. "
            f"I'm easing your target bedtime {BEDTIME_SHIFT_MINUTES} minutes later to {new_bedtime} "
            f"since you've earned a bit more flexibility."
        )
        adjusted = True
    else:
        new_bedtime = current_target_bedtime
        reason = f"Your average score is holding steady at {rolling_avg}/100. Keeping your current plan as-is."
        adjusted = False

    logger.info(
        "[PLAN_ENGINE] WEEKLY_COMPARISON result for user_id '%s': status=%s, adjusted=%s",
        user_id, status.value, adjusted
    )

    return PlanAdjustmentSchema(
        user_id=user_id,
        status=status,
        triggered_by=PlanTrigger.WEEKLY_COMPARISON,
        adjusted=adjusted,
        previous_target_bedtime=current_target_bedtime,
        new_target_bedtime=new_bedtime,
        rolling_avg_score=rolling_avg,
        previous_week_avg_score=previous_avg,
        reason=reason,
    )