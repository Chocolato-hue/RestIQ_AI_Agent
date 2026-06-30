"""Persist sleep logs and update user streaks."""

import datetime
import logging
import sqlite3
from datetime import date

from schemas import PlanStatus, SleepEntrySchema

from db.sqlite import DB_FILE

logger = logging.getLogger("tools.storage")


def store_sleep_data(entry: SleepEntrySchema | dict) -> None:
    logger.info("[STORAGE] store_sleep_data")
    validated = entry if isinstance(entry, SleepEntrySchema) else SleepEntrySchema(**entry)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO sleep_entries (
            user_id, date, bedtime, wake_time, sleep_duration, wake_up_count,
            sleep_quality, mood_on_wake, caffeine_after_2pm, exercise_today,
            screen_time_before_bed, focus_level, energy_level, notes, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            validated.user_id,
            validated.date.isoformat() if isinstance(validated.date, date) else validated.date,
            validated.bedtime,
            validated.wake_time,
            validated.sleep_duration,
            validated.wake_up_count,
            validated.sleep_quality.value,
            validated.mood_on_wake.value,
            1 if validated.caffeine_after_2pm else 0,
            1 if validated.exercise_today else 0,
            1 if validated.screen_time_before_bed else 0,
            validated.focus_level,
            validated.energy_level,
            validated.notes,
            validated.score,
        ),
    )

    cursor.execute(
        "SELECT check_in_streak, total_entries FROM users WHERE user_id = ?",
        (validated.user_id,),
    )
    user_row = cursor.fetchone()

    val_date_str = (
        validated.date.isoformat()
        if isinstance(validated.date, date)
        else validated.date
    )
    val_date = (
        validated.date
        if isinstance(validated.date, date)
        else datetime.datetime.strptime(validated.date, "%Y-%m-%d").date()
    )

    cursor.execute(
        """
        SELECT date FROM sleep_entries
        WHERE user_id = ? AND date < ?
        ORDER BY date DESC LIMIT 1
        """,
        (validated.user_id, val_date_str),
    )
    prev_row = cursor.fetchone()

    if not user_row:
        cursor.execute(
            """
            INSERT INTO users (
                user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
                caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                validated.user_id,
                f"User_{validated.user_id}",
                "07:00",
                "23:00",
                8.0,
                "MEDIUM",
                1,
                1,
                PlanStatus.INSUFFICIENT_DATA.value,
                None,
                datetime.datetime.now().isoformat(),
            ),
        )
    else:
        if prev_row:
            prev_date = datetime.datetime.strptime(prev_row[0], "%Y-%m-%d").date()
            diff = (val_date - prev_date).days
            if diff == 1:
                new_streak = user_row[0] + 1
            elif diff > 1:
                new_streak = 1
            else:
                new_streak = user_row[0]
        else:
            new_streak = 1

        cursor.execute(
            "SELECT COUNT(*) FROM sleep_entries WHERE user_id = ?",
            (validated.user_id,),
        )
        total_entries = cursor.fetchone()[0]

        cursor.execute(
            """
            UPDATE users
            SET check_in_streak = ?, total_entries = ?
            WHERE user_id = ?
            """,
            (new_streak, total_entries, validated.user_id),
        )

    conn.commit()
    conn.close()
