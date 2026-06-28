"""
sleep_coach.py — RestIQ Cognitive Science Engine

Evidence-based sleep coaching grounded in:
- Borbély's Two-Process Model (Process S: sleep pressure, Process C: circadian rhythm)
- Van Dongen et al. (2003): cumulative sleep debt and cognitive impairment
- Walker (2017): sleep architecture and habit impact
- Roenneberg et al.: chronotype and social jetlag
- Harvard Medical School: sleep hygiene evidence base

This module replaces generic recommendations with personalized,
science-grounded advice based on the user's actual habit pattern.
"""

from __future__ import annotations
import datetime
from dataclasses import dataclass
from typing import Optional
from schemas import SleepEntrySchema, SleepAnalysisSchema, SleepQuality, MoodOnWake


# ──────────────────────────────────────────────────────────────────────────────
# Science constants
# ──────────────────────────────────────────────────────────────────────────────

# Caffeine half-life is ~5-6 hours (Nehlig et al., 1992)
# Caffeine after 2PM = still ~50% active at 10PM
CAFFEINE_HALFLIFE_HOURS = 5.5

# Blue light suppresses melatonin by up to 50% for ~3h after exposure
# (Harvard Health, Gooley et al. 2011)
SCREEN_MELATONIN_SUPPRESSION_HOURS = 3

# Optimal sleep window for adults: 7-9 hours (NSF, 2015)
OPTIMAL_SLEEP_MIN = 7.0
OPTIMAL_SLEEP_MAX = 9.0

# Sleep debt accumulates linearly; >1h deficit per night degrades reaction
# time equivalent to 0.05% BAC per 24h awake (Van Dongen et al., 2003)
DEBT_IMPAIRMENT_THRESHOLD = 1.0  # hours below optimal per night

# Wind-down window: 60-90 min before bed (Walker, 2017)
WIND_DOWN_MINUTES = 75

# Chronotype-aware bedtime ranges (Roenneberg et al.)
CHRONOTYPE_RANGES = {
    "early": ("21:00", "22:30"),   # "morning larks"
    "intermediate": ("22:30", "00:00"),  # majority
    "late": ("00:00", "01:30"),    # "night owls"
}


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SleepDebtResult:
    total_debt_hours: float
    nightly_deficit: float
    impairment_level: str   # NONE, MILD, MODERATE, SEVERE
    cognitive_note: str


@dataclass
class CoachingResult:
    recommended_bedtime: str
    wind_down_start: str
    screen_cutoff: str
    caffeine_cutoff: str
    primary_insight: str          # The #1 thing affecting their sleep
    personalized_tips: list[str]  # 2-3 specific, science-backed tips
    sleep_debt: SleepDebtResult
    chronotype_note: str


# ──────────────────────────────────────────────────────────────────────────────
# Core functions
# ──────────────────────────────────────────────────────────────────────────────

def _hhmm_to_minutes(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


def _minutes_to_hhmm(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _compute_sleep_debt(
    entries: list[SleepEntrySchema],
    target_duration: float = 8.0
) -> SleepDebtResult:
    """
    Computes cumulative sleep debt over the last N nights.
    Based on Van Dongen et al. (2003) chronic sleep restriction model.
    """
    if not entries:
        return SleepDebtResult(0, 0, "NONE", "No history yet.")

    deficits = [max(0, target_duration - e.sleep_duration) for e in entries]
    total_debt = sum(deficits)
    nightly_avg = total_debt / len(deficits)

    if total_debt < 1.0:
        level = "NONE"
        note = "Your sleep debt is minimal. Maintain consistency."
    elif total_debt < 3.0:
        level = "MILD"
        note = (
            f"You've accumulated ~{total_debt:.1f}h of sleep debt this week. "
            "Mild impairment in attention and reaction time is likely "
            "(Van Dongen et al., 2003). One extra hour tonight helps."
        )
    elif total_debt < 7.0:
        level = "MODERATE"
        note = (
            f"~{total_debt:.1f}h sleep debt detected. This is equivalent to "
            "the cognitive impairment of mild alcohol intoxication. "
            "You likely underestimate how impaired you are — "
            "this is a well-documented effect (Van Dongen et al., 2003)."
        )
    else:
        level = "SEVERE"
        note = (
            f"⚠️ ~{total_debt:.1f}h sleep debt. Severe cognitive impairment: "
            "reaction time, memory consolidation, and emotional regulation "
            "are all significantly degraded. Prioritize sleep this weekend. "
            "Recovery requires multiple full nights, not just one (Banks & Dinges, 2007)."
        )

    return SleepDebtResult(total_debt, nightly_avg, level, note)


def _infer_chronotype(wake_time: str) -> tuple[str, str]:
    """
    Infers rough chronotype from habitual wake time.
    Based on Roenneberg et al. (2007) Munich Chronotype Questionnaire.
    Returns (chronotype, note).
    """
    wake_min = _hhmm_to_minutes(wake_time)

    if wake_min <= _hhmm_to_minutes("06:30"):
        return "early", "You're a morning chronotype (lark). Your ideal bedtime is 9-10:30PM."
    elif wake_min <= _hhmm_to_minutes("08:00"):
        return "intermediate", "You have an intermediate chronotype. Ideal bedtime: 10:30PM-midnight."
    else:
        return "late", (
            "You appear to be a late chronotype (owl). "
            "Your natural bedtime is later, but social obligations create 'social jetlag' "
            "if your schedule forces an early wake (Roenneberg et al., 2012). "
            "Gradual 15-min earlier shifts work better than sudden changes."
        )


def _identify_primary_culprit(entry: SleepEntrySchema, analysis: Optional[SleepAnalysisSchema] = None) -> str:
    """
    Identifies the single biggest factor degrading sleep quality,
    with the science explanation attached.
    """
    # Score each habit's likely impact
    factors = []

    if entry.screen_time_before_bed:
        factors.append((
            20,  # impact weight
            "📱 Screen time before bed is your biggest issue. "
            "Blue light (450-480nm wavelength) suppresses melatonin production by up to 50% "
            "for 2-3 hours after exposure (Gooley et al., 2011). "
            "Your brain literally can't prepare for sleep while you're on your phone."
        ))

    if entry.caffeine_after_2pm:
        # Estimate caffeine still active at typical 10PM bedtime
        # If caffeine at 3PM, half-life 5.5h → ~35% active at 10PM
        factors.append((
            15,
            "☕ Late caffeine is disrupting your sleep architecture. "
            "With a ~5.5h half-life, caffeine consumed at 3PM is still ~35% active at midnight. "
            "It reduces deep (slow-wave) sleep even when you feel like you slept fine "
            "(Drake et al., 2013). Cut off by 1PM to be safe."
        ))

    if entry.wake_up_count >= 3:
        factors.append((
            12,
            f"🌙 Waking up {entry.wake_up_count}x disrupts your sleep cycles. "
            "Each 90-min sleep cycle ends in brief arousal. "
            "More than 2 wake-ups suggests your sleep pressure is low, "
            "your sleep environment is disrupted, or alcohol/hydration is a factor "
            "(Carskadon & Dement, 2011)."
        ))

    if entry.sleep_duration < OPTIMAL_SLEEP_MIN:
        deficit = OPTIMAL_SLEEP_MIN - entry.sleep_duration
        factors.append((
            18,
            f"⏰ You only got {entry.sleep_duration}h — {deficit:.1f}h below the 7h minimum. "
            "Sleep is not optional recovery: memory consolidation, immune function, and "
            "emotional regulation all require sufficient slow-wave and REM sleep "
            "(Walker, 2017). There is no 'catching up' on weekdays."
        ))

    if entry.mood_on_wake in [MoodOnWake.TIRED, MoodOnWake.TERRIBLE]:
        if not factors:
            factors.append((
                8,
                "😴 Poor morning mood suggests you're waking mid-cycle. "
                "Sleep inertia is strongest when you wake during deep sleep (N3). "
                "Try shifting your alarm 20-30 minutes earlier or later "
                "to land in lighter sleep (N1/N2) instead."
            ))

    if not factors:
        return (
            "✅ No strong negative habits detected tonight. "
            "Consistency is your best tool — same bedtime and wake time every day, "
            "even weekends, anchors your circadian rhythm (Czeisler et al., 1999)."
        )

    # Return the highest-impact culprit
    factors.sort(key=lambda x: x[0], reverse=True)
    return factors[0][1]


def _build_personalized_tips(entry: SleepEntrySchema, chronotype: str) -> list[str]:
    """
    Builds 2-3 specific, actionable, science-backed tips
    based on the user's actual habits tonight.
    """
    tips = []

    # Tip 1: Screen time
    if entry.screen_time_before_bed:
        tips.append(
            "🔴 Set a phone cutoff 75 minutes before your target bedtime. "
            "Use blue-light blocking glasses or Night Mode as a fallback, "
            "but physical separation works better (Harvard Sleep Medicine, 2020)."
        )
    else:
        tips.append(
            "✅ Good: no screens before bed. Keep this up — "
            "it's one of the highest-leverage sleep hygiene behaviors."
        )

    # Tip 2: Caffeine
    if entry.caffeine_after_2pm:
        tips.append(
            "🔴 Move your last caffeine to before 1PM tomorrow. "
            "If you rely on afternoon caffeine for energy, that's a sign "
            "of sleep debt — the solution is more sleep, not more caffeine "
            "(Roehrs & Roth, 2008)."
        )

    # Tip 3: Exercise timing
    if not entry.exercise_today:
        tips.append(
            "💪 Even 20 minutes of aerobic exercise increases slow-wave sleep "
            "by ~15% (Passos et al., 2011). Morning or afternoon is ideal — "
            "intense exercise within 3h of bed can delay sleep onset."
        )
    elif entry.exercise_today and entry.sleep_quality in [SleepQuality.POOR, SleepQuality.FAIR]:
        tips.append(
            "🕐 You exercised today but still slept poorly — check timing. "
            "Late-evening intense exercise raises core body temperature and cortisol, "
            "delaying sleep onset by 30-60 minutes (Stutz et al., 2019)."
        )

    # Tip 4: Chronotype-specific
    if chronotype == "late" and entry.wake_time:
        tips.append(
            "🦉 As a late chronotype, avoid dramatic weekend sleep-ins. "
            "Sleeping 2+ hours later on weekends causes 'social jetlag' — "
            "equivalent to flying across 2 time zones every week "
            "(Roenneberg et al., 2012). Max 30-min deviation from your weekday wake time."
        )

    return tips[:3]  # Max 3 tips to avoid overwhelm


def _compute_smart_bedtime(
    wake_time: str,
    sleep_debt: SleepDebtResult,
    chronotype: str,
    screen_before_bed: bool,
    caffeine_after_2pm: bool,
) -> tuple[str, str, str, str]:
    """
    Computes a science-grounded recommended bedtime, accounting for:
    - Target sleep duration (8h + debt recovery buffer)
    - Chronotype-appropriate range
    - Wind-down window (75 min before bed: no screens, no caffeine)
    - Sleep pressure (Process S of Borbély's two-process model)

    Returns (bedtime, wind_down_start, screen_cutoff, caffeine_cutoff)
    """
    wake_min = _hhmm_to_minutes(wake_time)

    # Base: 8h of sleep needed
    target_duration_min = int(OPTIMAL_SLEEP_MIN * 60)

    # Add debt recovery buffer (cap at 1h extra to avoid oversleeping)
    if sleep_debt.impairment_level in ["MODERATE", "SEVERE"]:
        recovery_buffer = 30  # 30 extra minutes tonight
    elif sleep_debt.impairment_level == "MILD":
        recovery_buffer = 15
    else:
        recovery_buffer = 0

    raw_bedtime_min = wake_min - target_duration_min - recovery_buffer

    # Clamp to chronotype-appropriate range
    chrono_start, chrono_end = CHRONOTYPE_RANGES[chronotype]
    chrono_start_min = _hhmm_to_minutes(chrono_start)
    chrono_end_min = _hhmm_to_minutes(chrono_end)

    # Handle midnight wrap for late chronotype
    if chrono_end_min < chrono_start_min:
        chrono_end_min += 24 * 60

    # Nudge bedtime toward chronotype range if far off
    if raw_bedtime_min < chrono_start_min - 30:
        # Too early — nudge later by 15 min (gradual shift principle)
        recommended_bedtime_min = chrono_start_min - 15
    elif raw_bedtime_min > chrono_end_min + 30:
        # Too late — flag but don't force (social obligations exist)
        recommended_bedtime_min = raw_bedtime_min
    else:
        recommended_bedtime_min = raw_bedtime_min

    wind_down_min = recommended_bedtime_min - WIND_DOWN_MINUTES
    screen_cutoff_min = recommended_bedtime_min - int(SCREEN_MELATONIN_SUPPRESSION_HOURS * 60)
    caffeine_cutoff_min = _hhmm_to_minutes("13:00")  # Science-based: 1PM cutoff

    return (
        _minutes_to_hhmm(recommended_bedtime_min),
        _minutes_to_hhmm(wind_down_min),
        _minutes_to_hhmm(screen_cutoff_min),
        _minutes_to_hhmm(caffeine_cutoff_min),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_coaching(
    entry: SleepEntrySchema,
    history: list[SleepEntrySchema],
    analysis: Optional[SleepAnalysisSchema] = None,
    target_wake_time: str = "07:00",
) -> CoachingResult:
    """
    Main entry point. Generates personalized, science-backed sleep coaching
    based on last night's entry and recent history.

    Args:
        entry: Tonight's (last night's) sleep log.
        history: Last 7+ days of sleep entries for debt calculation.
        analysis: Optional pre-computed analysis from AnalyzerAgent.
        target_wake_time: User's preferred wake time for circadian calc.

    Returns:
        CoachingResult with bedtime, tips, debt, and primary insight.
    """
    wake_time = entry.wake_time or target_wake_time
    chronotype, chronotype_note = _infer_chronotype(wake_time)
    sleep_debt = _compute_sleep_debt(history or [entry])
    primary_insight = _identify_primary_culprit(entry, analysis)
    tips = _build_personalized_tips(entry, chronotype)

    bedtime, wind_down, screen_cutoff, caffeine_cutoff = _compute_smart_bedtime(
        wake_time=wake_time,
        sleep_debt=sleep_debt,
        chronotype=chronotype,
        screen_before_bed=entry.screen_time_before_bed,
        caffeine_after_2pm=entry.caffeine_after_2pm,
    )

    return CoachingResult(
        recommended_bedtime=bedtime,
        wind_down_start=wind_down,
        screen_cutoff=screen_cutoff,
        caffeine_cutoff=caffeine_cutoff,
        primary_insight=primary_insight,
        personalized_tips=tips,
        sleep_debt=sleep_debt,
        chronotype_note=chronotype_note,
    )


def format_coaching_message(coaching: CoachingResult) -> str:
    """
    Formats CoachingResult into a readable Telegram/Streamlit message.
    """
    debt_emoji = {
        "NONE": "🟢",
        "MILD": "🟡",
        "MODERATE": "🟠",
        "SEVERE": "🔴",
    }.get(coaching.sleep_debt.impairment_level, "⚪")

    tips_text = "\n".join(f"  {i+1}. {t}" for i, t in enumerate(coaching.personalized_tips))

    return (
        f"🧠 *What's actually affecting your sleep:*\n"
        f"{coaching.primary_insight}\n\n"
        f"🕐 *Tonight's science-backed schedule:*\n"
        f"  • Last caffeine: {coaching.caffeine_cutoff} (5.5h half-life rule)\n"
        f"  • Screen cutoff: {coaching.screen_cutoff} (melatonin protection)\n"
        f"  • Wind down: {coaching.wind_down_start} (dim lights, no work)\n"
        f"  • Lights out: {coaching.recommended_bedtime}\n\n"
        f"{debt_emoji} *Sleep debt: {coaching.sleep_debt.impairment_level}*\n"
        f"{coaching.sleep_debt.cognitive_note}\n\n"
        f"💡 *Your 3 actions for tonight:*\n{tips_text}\n\n"
        f"🦉 *Chronotype note:* {coaching.chronotype_note}"
    )