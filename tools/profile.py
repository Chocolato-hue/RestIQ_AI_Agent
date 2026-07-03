"""User profile registration and Telegram linking."""

import datetime
import logging
import sqlite3
from typing import Optional

from schemas import PlanStatus, TelegramLinkSchema, UserProfileSchema
from db.sqlite import DB_FILE

logger = logging.getLogger("tools.profile")


def register_user(
    user_id: str,
    username: str,
    target_wake_time: str = "07:00",
    age_years: Optional[float] = None,
) -> UserProfileSchema:
    logger.info("[PROFILE] register_user user_id=%s username=%s age=%s", user_id, username, age_years)
    if not user_id or not user_id.strip():
        raise ValueError("user_id must be a non-empty string.")

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    created_at = datetime.datetime.now().isoformat()

    cursor.execute(
        """
        INSERT OR IGNORE INTO users (
            user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
            caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at,
            telegram_chat_id, telegram_linked_at, preferred_checkin_time, created_at, age_years
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id, username, target_wake_time, "23:00", 8.0,
            "MEDIUM", 0, 0, PlanStatus.INSUFFICIENT_DATA.value, None,
            None, None, None, created_at, age_years
        ),
    )
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Failed to create profile for {user_id}")

    return UserProfileSchema(**dict(row))


def get_user_profile(user_id: str) -> UserProfileSchema:
    """Return full profile including age."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise ValueError(f"User {user_id} not found")
    return UserProfileSchema(**dict(row))


def link_telegram(user_id: str, telegram_chat_id: str) -> TelegramLinkSchema:
    logger.info("[PROFILE] link_telegram user_id=%s chat_id=%s", user_id, telegram_chat_id)
    if not user_id or not telegram_chat_id:
        raise ValueError("user_id and telegram_chat_id must both be non-empty.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_chat_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    already_linked = bool(row and row[0])
    linked_at = datetime.datetime.now()

    if row is None:
        cursor.execute(
            """
            INSERT INTO users (
                user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
                caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at,
                telegram_chat_id, telegram_linked_at, preferred_checkin_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                f"User_{user_id}",
                "07:00",
                "23:00",
                8.0,
                "MEDIUM",
                0,
                0,
                PlanStatus.INSUFFICIENT_DATA.value,
                None,
                telegram_chat_id,
                linked_at.isoformat(),
                None,
                linked_at.isoformat(),
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE users SET telegram_chat_id = ?, telegram_linked_at = ? WHERE user_id = ?
            """,
            (telegram_chat_id, linked_at.isoformat(), user_id),
        )

    conn.commit()
    conn.close()

    return TelegramLinkSchema(
        user_id=user_id,
        telegram_chat_id=telegram_chat_id,
        already_linked=already_linked,
        linked_at=linked_at,
    )


def get_telegram_chat_id(user_id: str) -> str | None:
    """Return the linked Telegram chat_id for *user_id*, or None if not linked."""
    logger.debug("[PROFILE] get_telegram_chat_id user_id=%s", user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT telegram_chat_id FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        return str(row[0])
    return None


def get_user_age(user_id: str) -> float | None:
    """Return the stored age_years for *user_id*, or None if not yet provided."""
    logger.debug("[PROFILE] get_user_age user_id=%s", user_id)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT age_years FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] is not None:
        return float(row[0])
    return None


def update_user_age(user_id: str, age_years: float) -> None:
    """Persist *age_years* to the users row for *user_id*."""
    if age_years < 0 or age_years > 130:
        raise ValueError(f"age_years must be between 0 and 130, got {age_years}.")
    logger.info("[PROFILE] update_user_age user_id=%s age_years=%s", user_id, age_years)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET age_years = ? WHERE user_id = ?", (age_years, user_id)
    )
    conn.commit()
    conn.close()


def store_sleep_assessment(user_id: str, assessment: dict) -> None:
    """Persist a guideline assessment record to *sleep_assessments*.

    *assessment* must be the dict returned by
    ``tools.sleep_guideline.evaluate_duration_against_guideline()``,
    enriched with ``avg_hours`` and ``analyzed_at`` by the caller.
    VerdictLabel values must already be serialised to strings before calling.
    """
    import datetime as _dt

    logger.info("[PROFILE] store_sleep_assessment user_id=%s verdict=%s", user_id, assessment.get("verdict"))
    verdict = assessment.get("verdict", "")
    if hasattr(verdict, "value"):
        verdict = verdict.value

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO sleep_assessments (
            user_id, age_years, avg_hours, age_band,
            recommended_min_hours, recommended_max_hours,
            within_range, verdict, note, source, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            assessment.get("age_years"),
            assessment.get("avg_hours"),
            assessment.get("age_band"),
            assessment.get("recommended_min_hours"),
            assessment.get("recommended_max_hours"),
            int(bool(assessment.get("within_range", False))),
            verdict,
            assessment.get("note"),
            assessment.get("source"),
            assessment.get("analyzed_at", _dt.datetime.now().isoformat()),
        ),
    )
    conn.commit()
    conn.close()

