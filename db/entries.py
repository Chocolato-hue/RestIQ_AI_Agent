"""Helpers for loading and persisting sleep entries."""

import sqlite3
from datetime import date

from schemas import SleepEntrySchema

from db.sqlite import DB_FILE
from tools.scoring import compute_sleep_score


def row_to_entry(row: sqlite3.Row) -> SleepEntrySchema:
    e_dict = dict(row)
    e_dict["caffeine_after_2pm"] = bool(e_dict["caffeine_after_2pm"])
    e_dict["exercise_today"] = bool(e_dict["exercise_today"])
    e_dict["screen_time_before_bed"] = bool(e_dict["screen_time_before_bed"])
    return SleepEntrySchema(**e_dict)


def ensure_entry_scores(entries: list[SleepEntrySchema]) -> list[SleepEntrySchema]:
    for entry in entries:
        if entry.score is not None:
            continue
        entry.score = compute_sleep_score(entry)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sleep_entries SET score = ? WHERE user_id = ? AND date = ?",
            (
                entry.score,
                entry.user_id,
                entry.date.isoformat() if isinstance(entry.date, date) else entry.date,
            ),
        )
        conn.commit()
        conn.close()
    return entries


def fetch_recent_entries(user_id: str, days: int) -> list[SleepEntrySchema]:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM sleep_entries
        WHERE user_id = ?
        ORDER BY date DESC LIMIT ?
        """,
        (user_id, days),
    )
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return []
    return ensure_entry_scores([row_to_entry(r) for r in rows])
