"""SQLite database setup for RestIQ."""

import logging
import sqlite3

logger = logging.getLogger("services.db")

DB_FILE = "sleep_data.db"


def init_db() -> None:
    logger.info("[DB] Initializing SQLite database %s", DB_FILE)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sleep_entries (
        user_id TEXT,
        date TEXT,
        bedtime TEXT,
        wake_time TEXT,
        sleep_duration REAL,
        wake_up_count INTEGER,
        sleep_quality TEXT,
        mood_on_wake TEXT,
        caffeine_after_2pm INTEGER,
        exercise_today INTEGER,
        screen_time_before_bed INTEGER,
        focus_level INTEGER,
        energy_level INTEGER,
        notes TEXT,
        score INTEGER,
        PRIMARY KEY (user_id, date)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT,
        target_wake_time TEXT,
        target_bedtime TEXT,
        target_sleep_duration REAL,
        caffeine_sensitivity TEXT,
        check_in_streak INTEGER,
        total_entries INTEGER,
        plan_status TEXT,
        plan_updated_at TEXT,
        telegram_chat_id TEXT,
        telegram_linked_at TEXT,
        preferred_checkin_time TEXT,
        created_at TEXT
    )
    """)

    def _ensure_column(table: str, column: str, col_type: str, default_sql: str = "NULL") -> None:
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if column not in existing_cols:
            logger.info("[DB] Migrating: adding column '%s' to table '%s'", column, table)
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default_sql}")

    _ensure_column("sleep_entries", "focus_level", "INTEGER", "3")
    _ensure_column("sleep_entries", "energy_level", "INTEGER", "3")
    _ensure_column("users", "target_bedtime", "TEXT", "'23:00'")
    _ensure_column("users", "plan_status", "TEXT", "'INSUFFICIENT_DATA'")
    _ensure_column("users", "plan_updated_at", "TEXT", "NULL")
    _ensure_column("users", "telegram_chat_id", "TEXT", "NULL")
    _ensure_column("users", "telegram_linked_at", "TEXT", "NULL")
    _ensure_column("users", "preferred_checkin_time", "TEXT", "NULL")

    conn.commit()
    conn.close()
