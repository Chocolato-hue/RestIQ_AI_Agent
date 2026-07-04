"""Sleep pattern analysis over a rolling window."""

import logging
import sqlite3

from schemas import SleepAnalysisSchema, SleepEntrySchema

from tools.analysis import build_sleep_analysis
from db.sqlite import DB_FILE
from db.entries import fetch_recent_entries
from tools.profile import get_user_age

logger = logging.getLogger("tools.analyzer")


def analyze_patterns(user_id: str, days: int = 7) -> tuple[SleepAnalysisSchema, list[SleepEntrySchema]]:
    logger.info("[ANALYZER] analyze_patterns user_id=%s days=%d", user_id, days)

    entries = fetch_recent_entries(user_id, days)
    if not entries:
        raise ValueError(f"No sleep entries found for user {user_id}...")

    # Better: get full profile
    profile = get_user_profile(user_id)   # Use this instead of separate queries
    streak_days = profile.check_in_streak
    age_years = profile.age_years

    analysis = build_sleep_analysis(
        user_id, days, entries, streak_days, age_years=age_years
    )
    
    return analysis, entries
