"""Adaptive sleep plan evaluation and persistence."""

import datetime
import logging
import sqlite3

import plan_engine
from schemas import PlanAdjustmentSchema

from services.db import DB_FILE

logger = logging.getLogger("services.plan")


def evaluate_plan(user_id: str, commit_weekly_adjustment: bool = False) -> PlanAdjustmentSchema:
    logger.info(
        "[PLAN] evaluate_plan user_id=%s commit_weekly_adjustment=%s",
        user_id,
        commit_weekly_adjustment,
    )

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT target_bedtime FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    current_target_bedtime = (
        user_row["target_bedtime"] if user_row and user_row["target_bedtime"] else "23:00"
    )

    cursor.execute(
        """
        SELECT date, score FROM sleep_entries
        WHERE user_id = ? AND score IS NOT NULL
        ORDER BY date DESC LIMIT 14
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    scores_recent_first = [row["score"] for row in rows]

    adjustment = plan_engine.evaluate_plan(
        user_id=user_id,
        scores_recent_first=scores_recent_first,
        current_target_bedtime=current_target_bedtime,
        commit_weekly_adjustment=commit_weekly_adjustment,
    )

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    if adjustment.adjusted:
        cursor.execute(
            """
            UPDATE users
            SET target_bedtime = ?, plan_status = ?, plan_updated_at = ?
            WHERE user_id = ?
            """,
            (
                adjustment.new_target_bedtime,
                adjustment.status.value,
                datetime.datetime.now().isoformat(),
                user_id,
            ),
        )
        logger.info(
            "[PLAN] Adjusted user_id=%s: %s -> %s (%s)",
            user_id,
            adjustment.previous_target_bedtime,
            adjustment.new_target_bedtime,
            adjustment.triggered_by.value,
        )
    else:
        cursor.execute(
            "UPDATE users SET plan_status = ? WHERE user_id = ?",
            (adjustment.status.value, user_id),
        )

    conn.commit()
    conn.close()
    return adjustment
