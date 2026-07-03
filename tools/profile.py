"""User profile registration and Telegram linking."""

import datetime
import logging
import sqlite3

from schemas import PlanStatus, TelegramLinkSchema, UserProfileSchema

from db.sqlite import DB_FILE

logger = logging.getLogger("tools.profile")


def register_user(
    user_id: str,
    username: str,
    target_wake_time: str = "07:00",
) -> UserProfileSchema:
    logger.info("[PROFILE] register_user user_id=%s username=%s", user_id, username)
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
            telegram_chat_id, telegram_linked_at, preferred_checkin_time, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            target_wake_time,
            "23:00",
            8.0,
            "MEDIUM",
            0,
            0,
            PlanStatus.INSUFFICIENT_DATA.value,
            None,
            None,
            None,
            None,
            created_at,
        ),
    )
    conn.commit()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"Failed to create or find user profile for user_id '{user_id}'.")

    return UserProfileSchema(
        user_id=row["user_id"],
        username=row["username"],
        target_wake_time=row["target_wake_time"],
        target_bedtime=row["target_bedtime"],
        target_sleep_duration=row["target_sleep_duration"],
        caffeine_sensitivity=row["caffeine_sensitivity"],
        check_in_streak=row["check_in_streak"],
        total_entries=row["total_entries"],
        plan_status=row["plan_status"],
        plan_updated_at=row["plan_updated_at"],
        telegram_chat_id=row["telegram_chat_id"],
        telegram_linked_at=row["telegram_linked_at"],
        preferred_checkin_time=row["preferred_checkin_time"],
        created_at=row["created_at"],
    )

def link_telegram(user_id: str, telegram_chat_id: str) -> TelegramLinkSchema:
    logger.info("[PROFILE] link_telegram user_id=%s chat_id=%s", user_id, telegram_chat_id)
    if not user_id or not telegram_chat_id:
        raise ValueError("user_id and telegram_chat_id must both be non-empty.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    linked_at = datetime.datetime.now()

    cursor.execute("SELECT telegram_chat_id FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    already_linked = bool(row and row[0] == telegram_chat_id)

    # Ensure one Telegram chat is linked to only one RestIQ user.
    cursor.execute(
        """
        UPDATE users
        SET telegram_chat_id = NULL, telegram_linked_at = NULL
        WHERE telegram_chat_id = ? AND user_id != ?
        """,
        (telegram_chat_id, user_id),
    )

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
            UPDATE users
            SET telegram_chat_id = ?, telegram_linked_at = ?
            WHERE user_id = ?
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
