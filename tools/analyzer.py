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
        raise ValueError(f"No sleep entries found for user {user_id} in the last {days} days.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT check_in_streak FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    conn.close()
    streak_days = user_row[0] if user_row else 0

    age_years = get_user_age(user_id)
    analysis = build_sleep_analysis(user_id, days, entries, streak_days, age_years=age_years)
    return analysis, entries
