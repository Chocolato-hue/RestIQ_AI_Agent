import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import json
import sqlite3
import logging
import datetime
from datetime import date
import pathlib
import dotenv
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mcp_server")

# Import schemas and enums
from schemas import (
    SleepEntrySchema,
    UserProfileSchema,
    CircadianSchema,
    SmartFollowUpSchema,
    SleepAnalysisSchema,
    WeeklyReportSchema,
    MCPToolResponseSchema,
    PlanAdjustmentSchema,
    TelegramLinkSchema,
    PlanStatus,
    SleepQuality,
    MoodOnWake,
    VerdictLabel,
    CaffeineSensitivity
)

# Import plan decision logic (kept separate from this transport/MCP layer)
import plan_engine

# Initialize MCP server
mcp = FastMCP("restiq-sleep-server")

DB_FILE = "sleep_data.db"

def init_db():
    logger.info("[MCP] Initializing SQLite database sleep_data.db")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Create sleep_entries table containing all SleepEntrySchema fields
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
    
    # Create users table
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
    
    # Lightweight migration: add new columns to pre-existing databases that
    # were created before this version (CREATE TABLE IF NOT EXISTS won't
    # retroactively add columns to a table that already exists).
    def _ensure_column(table: str, column: str, col_type: str, default_sql: str = "NULL"):
        cursor.execute(f"PRAGMA table_info({table})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if column not in existing_cols:
            logger.info("[MCP] Migrating: adding column '%s' to table '%s'", column, table)
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

# Initialize DB on load
init_db()


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

def calculate_duration(bedtime_str: str, wake_time_str: str) -> float:
    """Calculates sleep duration in hours from bedtime to wake_time handling midnight wrap."""
    try:
        bt_h, bt_m = map(int, bedtime_str.split(':'))
        wt_h, wt_m = map(int, wake_time_str.split(':'))
        bt_total = bt_h + bt_m / 60.0
        wt_total = wt_h + wt_m / 60.0
        if wt_total >= bt_total:
            duration = wt_total - bt_total
        else:
            duration = (wt_total + 24.0) - bt_total
        return round(duration, 2)
    except Exception as e:
        raise ValueError(f"Failed to calculate sleep duration from bedtime '{bedtime_str}' and wake_time '{wake_time_str}': {e}")


def compute_sleep_score(entry: SleepEntrySchema) -> int:
    """Computes a baseline sleep score from 0 to 100 based on habits and sleep details."""
    score = 100
    
    # Duration deduction (ideal sleep is around 8 hours)
    duration = entry.sleep_duration
    if duration < 7.0:
        score -= int((7.0 - duration) * 15)
    elif duration > 9.0:
        score -= int((duration - 9.0) * 10)
        
    # Wake up count deduction (deduct 8 pts per wake-up)
    score -= entry.wake_up_count * 8
    
    # Quality adjustment
    quality_map = {
        SleepQuality.POOR: -30,
        SleepQuality.FAIR: -10,
        SleepQuality.GOOD: 5,
        SleepQuality.EXCELLENT: 15
    }
    score += quality_map.get(entry.sleep_quality, 0)
    
    # Habits impact
    if entry.screen_time_before_bed:
        score -= 15
    if entry.caffeine_after_2pm:
        score -= 10
    if entry.exercise_today:
        score += 10
        
    return max(0, min(100, score))


# ──────────────────────────────────────────────────────────────────────────────
# MCP Tools
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def register_user(user_id: str, username: str, target_wake_time: str = "07:00") -> dict:
    """
    Profile Agent tool (web registration).
    Creates a new user profile with sensible defaults, intended to be called
    when someone signs up on the web dashboard BEFORE their first check-in
    (unlike the legacy path in store_sleep_data, which only ever created a
    user row as a side effect of a first sleep log). Idempotent: calling this
    again for an existing user_id leaves their existing row untouched rather
    than overwriting their progress.
    Return MCPToolResponseSchema with the resulting UserProfileSchema as dict.
    """
    logger.info("[MCP] register_user called for user_id: %s, username: %s", user_id, username)
    try:
        if not user_id or not user_id.strip():
            raise ValueError("user_id must be a non-empty string.")

        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        created_at = datetime.datetime.now().isoformat()

        # INSERT OR IGNORE: if this user_id already exists (e.g. the person
        # re-registers, or registered then later checked in), this is a no-op
        # rather than clobbering their existing streak/plan/Telegram link.
        cursor.execute("""
        INSERT OR IGNORE INTO users (
            user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
            caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at,
            telegram_chat_id, telegram_linked_at, preferred_checkin_time, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
            created_at
        ))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError(f"Failed to create or find user profile for user_id '{user_id}'.")

        profile = UserProfileSchema(
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

        tool_response = MCPToolResponseSchema(
            tool_name="register_user",
            success=True,
            data=profile.model_dump(mode="json"),
            error=None,
            agent_next=None
        )
        return tool_response.model_dump(mode="json")

    except Exception as e:
        logger.error("[MCP] Error in register_user: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="register_user",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def link_telegram(user_id: str, telegram_chat_id: str) -> dict:
    """
    Profile Agent tool (Telegram linking).
    Records that a web-registered user_id should receive Telegram
    notifications at the given chat_id. Called by bot.py when a user starts
    the bot via a deep link of the form /start <user_id> (the payload is the
    user_id assigned during web registration). If user_id doesn't exist yet
    (someone linked Telegram before ever registering on the web), creates a
    minimal profile so the link isn't silently dropped. Re-linking the same
    user_id to a new chat_id overwrites the previous chat_id (one active
    Telegram link per user_id at a time).
    Return MCPToolResponseSchema with TelegramLinkSchema as dict.
    """
    logger.info("[MCP] link_telegram called for user_id: %s, telegram_chat_id: %s", user_id, telegram_chat_id)
    try:
        if not user_id or not telegram_chat_id:
            raise ValueError("user_id and telegram_chat_id must both be non-empty.")

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT telegram_chat_id FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        already_linked = bool(row and row[0])
        linked_at = datetime.datetime.now()

        if row is None:
            # No profile yet (Telegram-first path) — create a minimal one so
            # the link has somewhere to attach, consistent with the defaults
            # register_user would otherwise have set up.
            cursor.execute("""
            INSERT INTO users (
                user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
                caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at,
                telegram_chat_id, telegram_linked_at, preferred_checkin_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                linked_at.isoformat()
            ))
        else:
            cursor.execute("""
            UPDATE users SET telegram_chat_id = ?, telegram_linked_at = ? WHERE user_id = ?
            """, (telegram_chat_id, linked_at.isoformat(), user_id))

        conn.commit()
        conn.close()

        link_result = TelegramLinkSchema(
            user_id=user_id,
            telegram_chat_id=telegram_chat_id,
            already_linked=already_linked,
            linked_at=linked_at,
        )

        tool_response = MCPToolResponseSchema(
            tool_name="link_telegram",
            success=True,
            data=link_result.model_dump(mode="json"),
            error=None,
            agent_next=None
        )
        return tool_response.model_dump(mode="json")

    except Exception as e:
        logger.error("[MCP] Error in link_telegram: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="link_telegram",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def parse_sleep_input(user_id: str, raw_text: str) -> dict:
    """
    Intake Agent tool.
    Parse natural language sleep input into structured SleepEntrySchema.
    Use Gemini to extract: bedtime, wake_time, wake_up_count,
    sleep_quality, mood_on_wake, caffeine_after_2pm,
    exercise_today, screen_time_before_bed, focus_level, energy_level, notes.
    Calculate sleep_duration from bedtime to wake_time.
    Return MCPToolResponseSchema as dict.
    """
    logger.info("[MCP] parse_sleep_input called with user_id: %s", user_id)
    try:
        from google import genai
        from google.genai import types
        from pydantic import BaseModel, Field
        from typing import Optional
        
        # Define the Pydantic schema to pass to Gemini for structured extraction
        class SleepExtractionSchema(BaseModel):
            bedtime: str = Field(..., description="Bedtime in HH:MM format (24-hour clock)")
            wake_time: str = Field(..., description="Wake time in HH:MM format (24-hour clock)")
            wake_up_count: int = Field(..., ge=0, le=10, description="Number of times user woke up during the night (0-10)")
            sleep_quality: SleepQuality = Field(..., description="Self-reported sleep quality rating")
            mood_on_wake: MoodOnWake = Field(..., description="Self-reported mood upon waking")
            caffeine_after_2pm: bool = Field(..., description="Whether caffeine was consumed after 2:00 PM")
            exercise_today: bool = Field(..., description="Whether the user exercised during the day")
            screen_time_before_bed: bool = Field(..., description="Whether the user had screen time within 1 hour before bed")
            focus_level: int = Field(..., ge=1, le=5, description="Focus/concentration level today, inferred from explicit statements only (1=very poor, 5=excellent)")
            energy_level: int = Field(..., ge=1, le=5, description="Energy level today, inferred from explicit statements only (1=very low, 5=excellent)")
            notes: Optional[str] = Field(None, description="Any additional notes or observations")

        system_instruction = (
            "You are an expert sleep data extraction assistant.\n"
            "Analyze the user's natural language check-in text and extract structured sleep information.\n"
            "Strictly extract all required fields into the requested JSON schema.\n"
            "If any value is not explicitly mentioned, estimate it reasonably based on context or use standard sensible defaults:\n"
            "- bedtime: HH:MM format (24-hour clock)\n"
            "- wake_time: HH:MM format (24-hour clock)\n"
            "- wake_up_count: integer (0-10)\n"
            "- sleep_quality: POOR, FAIR, GOOD, or EXCELLENT\n"
            "- mood_on_wake: TERRIBLE, TIRED, OKAY, GOOD, or GREAT\n"
            "- caffeine_after_2pm: boolean (true/false)\n"
            "- exercise_today: boolean (true/false)\n"
            "- screen_time_before_bed: boolean (true/false)\n"
            "- focus_level: integer 1-5. Only infer this from explicit statements about concentration, "
            "distraction, or mental clarity (e.g. 'couldn't focus' -> low, 'sharp all day' -> high). "
            "If the user says nothing relevant to focus, use 3 (neutral) rather than guessing.\n"
            "- energy_level: integer 1-5. Only infer this from explicit statements about tiredness, "
            "fatigue, or energy (e.g. 'exhausted', 'felt sluggish' -> low, 'felt great, lots of energy' -> high). "
            "If the user says nothing relevant to energy, use 3 (neutral) rather than guessing.\n"
            "- notes: str or null"
        )
        
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable is not set.")
            
        client = genai.Client(api_key=api_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        
        response = client.models.generate_content(
            model=model_name,
            contents=raw_text,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=SleepExtractionSchema,
                temperature=0.0,
            )
        )
        
        extracted = response.parsed
        if not extracted:
            raise ValueError(f"Failed to parse structured output from Gemini. Raw text: {response.text}")
            
        duration = calculate_duration(extracted.bedtime, extracted.wake_time)
        
        sleep_entry = SleepEntrySchema(
            user_id=user_id,
            date=date.today(),
            bedtime=extracted.bedtime,
            wake_time=extracted.wake_time,
            sleep_duration=duration,
            wake_up_count=extracted.wake_up_count,
            sleep_quality=extracted.sleep_quality,
            mood_on_wake=extracted.mood_on_wake,
            caffeine_after_2pm=extracted.caffeine_after_2pm,
            exercise_today=extracted.exercise_today,
            screen_time_before_bed=extracted.screen_time_before_bed,
            focus_level=extracted.focus_level,
            energy_level=extracted.energy_level,
            notes=extracted.notes,
            score=None
        )
        
        tool_response = MCPToolResponseSchema(
            tool_name="parse_sleep_input",
            success=True,
            data=sleep_entry.model_dump(mode="json"),
            error=None,
            agent_next="TrackerAgent"
        )
        return tool_response.model_dump(mode="json")
        
    except Exception as e:
        logger.error("[MCP] Error in parse_sleep_input: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="parse_sleep_input",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def calculate_circadian(wake_time: str, sleep_duration: float = 8.0) -> dict:
    """
    Scheduler Agent tool.
    Calculate recommended bedtime = wake_time minus sleep_duration.
    Calculate wind_down_start = bedtime minus 15 minutes.
    Return CircadianSchema as dict wrapped in MCPToolResponseSchema.
    """
    logger.info("[MCP] calculate_circadian called with wake_time: %s, sleep_duration: %s", wake_time, sleep_duration)
    try:
        h, m = map(int, wake_time.split(':'))
        wake_minutes = h * 60 + m
        
        bedtime_minutes = int(wake_minutes - (sleep_duration * 60)) % (24 * 60)
        wind_down_minutes = (bedtime_minutes - 15) % (24 * 60)
        
        recommended_bedtime = f"{bedtime_minutes // 60:02d}:{bedtime_minutes % 60:02d}"
        recommended_wake_time = f"{h:02d}:{m:02d}"
        wind_down_start = f"{wind_down_minutes // 60:02d}:{wind_down_minutes % 60:02d}"
        
        circadian = CircadianSchema(
            recommended_bedtime=recommended_bedtime,
            recommended_wake_time=recommended_wake_time,
            sleep_window_hours=float(sleep_duration),
            wind_down_start=wind_down_start,
            notes=(
                f"To wake up rested at {recommended_wake_time} with {sleep_duration} hours of sleep, "
                f"aim to sleep by {recommended_bedtime} and start winding down at {wind_down_start}."
            )
        )
        
        tool_response = MCPToolResponseSchema(
            tool_name="calculate_circadian",
            success=True,
            data=circadian.model_dump(mode="json"),
            error=None,
            agent_next=None
        )
        return tool_response.model_dump(mode="json")
        
    except Exception as e:
        logger.error("[MCP] Error in calculate_circadian: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="calculate_circadian",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def store_sleep_data(entry: dict) -> dict:
    """
    Tracker Agent tool.
    Validate entry as SleepEntrySchema (including focus_level/energy_level).
    Insert into sleep_entries SQLite table.
    Update user check_in_streak and total_entries.
    Return MCPToolResponseSchema with success status.
    """
    logger.info("[MCP] store_sleep_data called")
    try:
        validated = SleepEntrySchema(**entry)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("""
        INSERT OR REPLACE INTO sleep_entries (
            user_id, date, bedtime, wake_time, sleep_duration, wake_up_count,
            sleep_quality, mood_on_wake, caffeine_after_2pm, exercise_today,
            screen_time_before_bed, focus_level, energy_level, notes, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
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
            validated.score
        ))
        
        # Retrieve or create user profile
        cursor.execute("SELECT check_in_streak, total_entries FROM users WHERE user_id = ?", (validated.user_id,))
        user_row = cursor.fetchone()
        
        val_date_str = validated.date.isoformat() if isinstance(validated.date, date) else validated.date
        val_date = validated.date if isinstance(validated.date, date) else datetime.datetime.strptime(validated.date, "%Y-%m-%d").date()
        
        # Get previous sleep log date (strictly before current log date)
        cursor.execute("""
        SELECT date FROM sleep_entries 
        WHERE user_id = ? AND date < ? 
        ORDER BY date DESC LIMIT 1
        """, (validated.user_id, val_date_str))
        prev_row = cursor.fetchone()
        
        if not user_row:
            # Create default user profile
            cursor.execute("""
            INSERT INTO users (
                user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
                caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                datetime.datetime.now().isoformat()
            ))
        else:
            if prev_row:
                prev_date = datetime.datetime.strptime(prev_row[0], "%Y-%m-%d").date()
                diff = (val_date - prev_date).days
                if diff == 1:
                    new_streak = user_row[0] + 1
                elif diff > 1:
                    new_streak = 1
                else:
                    new_streak = user_row[0] # older or same day entry, streak remains same
            else:
                new_streak = 1
                
            cursor.execute("SELECT COUNT(*) FROM sleep_entries WHERE user_id = ?", (validated.user_id,))
            total_entries = cursor.fetchone()[0]
            
            cursor.execute("""
            UPDATE users 
            SET check_in_streak = ?, total_entries = ? 
            WHERE user_id = ?
            """, (new_streak, total_entries, validated.user_id))
            
        conn.commit()
        conn.close()
        
        tool_response = MCPToolResponseSchema(
            tool_name="store_sleep_data",
            success=True,
            data={"message": "Sleep entry successfully recorded", "user_id": validated.user_id},
            error=None,
            agent_next="AnalyzerAgent"
        )
        return tool_response.model_dump(mode="json")
        
    except Exception as e:
        logger.error("[MCP] Error in store_sleep_data: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="store_sleep_data",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def evaluate_plan(user_id: str, commit_weekly_adjustment: bool = False) -> dict:
    """
    Scheduler Agent tool (adaptive plan).
    Fetches the user's recent sleep scores (most-recent-first) and current
    target_bedtime, then delegates the actual decision logic to plan_engine.
    Rule order: streak override (3 consecutive nights < 50) > rolling 7-day
    trend vs previous 7-day window. The rolling trend only commits a target
    bedtime change when commit_weekly_adjustment=True (i.e. called from the
    weekly report flow); daily check-ins pass False so the trend is reported
    without nudging the plan every single day. A confirmed streak override
    always commits regardless of commit_weekly_adjustment.
    Persists any committed change to the users table (target_bedtime,
    plan_status, plan_updated_at).
    Return PlanAdjustmentSchema as dict wrapped in MCPToolResponseSchema.
    """
    logger.info(
        "[MCP] evaluate_plan called for user_id: %s, commit_weekly_adjustment: %s",
        user_id, commit_weekly_adjustment
    )
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT target_bedtime FROM users WHERE user_id = ?", (user_id,)
        )
        user_row = cursor.fetchone()
        current_target_bedtime = user_row["target_bedtime"] if user_row and user_row["target_bedtime"] else "23:00"

        # Up to 14 most recent scored nights, most-recent-first, to support
        # both the streak check (last 3) and the rolling 7-vs-7 comparison.
        cursor.execute("""
        SELECT date, score FROM sleep_entries
        WHERE user_id = ? AND score IS NOT NULL
        ORDER BY date DESC LIMIT 14
        """, (user_id,))
        rows = cursor.fetchall()
        conn.close()

        scores_recent_first = [row["score"] for row in rows]

        adjustment = plan_engine.evaluate_plan(
            user_id=user_id,
            scores_recent_first=scores_recent_first,
            current_target_bedtime=current_target_bedtime,
            commit_weekly_adjustment=commit_weekly_adjustment,
        )

        if adjustment.adjusted:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE users
            SET target_bedtime = ?, plan_status = ?, plan_updated_at = ?
            WHERE user_id = ?
            """, (
                adjustment.new_target_bedtime,
                adjustment.status.value,
                datetime.datetime.now().isoformat(),
                user_id
            ))
            conn.commit()
            conn.close()
            logger.info(
                "[MCP] Plan adjusted for user_id '%s': %s -> %s (%s)",
                user_id, adjustment.previous_target_bedtime, adjustment.new_target_bedtime, adjustment.triggered_by.value
            )
        else:
            # Even without an adjustment, keep plan_status current so the
            # stored profile reflects the latest known trend.
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET plan_status = ? WHERE user_id = ?",
                (adjustment.status.value, user_id)
            )
            conn.commit()
            conn.close()

        tool_response = MCPToolResponseSchema(
            tool_name="evaluate_plan",
            success=True,
            data=adjustment.model_dump(mode="json"),
            error=None,
            agent_next="ReporterAgent"
        )
        return tool_response.model_dump(mode="json")

    except Exception as e:
        logger.error("[MCP] Error in evaluate_plan: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="evaluate_plan",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def analyze_patterns(user_id: str, days: int = 7) -> dict:
    """
    Analyzer Agent tool.
    Fetch last N days of sleep entries for user_id from SQLite.
    Calculate: average_score, average_duration, average_wake_ups.
    Find best_night (highest score) and worst_night (lowest score).
    Detect patterns:
    - If caffeine_after_2pm correlates with low scores → add pattern
    - If screen_time_before_bed correlates with low scores → add pattern
    - If exercise_today correlates with high scores → add pattern
    Score verdict: NEEDS_ATTENTION <50, IMPROVING 50-65,
    ON_TRACK 66-80, EXCELLENT >80.
    Return SleepAnalysisSchema as dict wrapped in MCPToolResponseSchema.
    """
    logger.info("[MCP] analyze_patterns called for user_id: %s, days: %d", user_id, days)
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM sleep_entries 
        WHERE user_id = ? 
        ORDER BY date DESC LIMIT ?
        """, (user_id, days))
        rows = cursor.fetchall()
        
        cursor.execute("SELECT check_in_streak FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        streak_days = user_row[0] if user_row else 0
        conn.close()
        
        if not rows:
            raise ValueError(f"No sleep entries found for user {user_id} in the last {days} days.")
            
        entries = []
        for r in rows:
            e_dict = dict(r)
            e_dict["caffeine_after_2pm"] = bool(e_dict["caffeine_after_2pm"])
            e_dict["exercise_today"] = bool(e_dict["exercise_today"])
            e_dict["screen_time_before_bed"] = bool(e_dict["screen_time_before_bed"])
            entry = SleepEntrySchema(**e_dict)
            
            # Populate score if missing
            if entry.score is None:
                entry.score = compute_sleep_score(entry)
                conn_upd = sqlite3.connect(DB_FILE)
                cursor_upd = conn_upd.cursor()
                cursor_upd.execute(
                    "UPDATE sleep_entries SET score = ? WHERE user_id = ? AND date = ?",
                    (entry.score, entry.user_id, entry.date.isoformat() if isinstance(entry.date, date) else entry.date)
                )
                conn_upd.commit()
                conn_upd.close()
                
            entries.append(entry)
            
        scores = [e.score for e in entries]
        durations = [e.sleep_duration for e in entries]
        wake_ups = [e.wake_up_count for e in entries]
        
        average_score = sum(scores) / len(scores)
        average_duration = sum(durations) / len(durations)
        average_wake_ups = sum(wake_ups) / len(wake_ups)
        
        best_night = max(entries, key=lambda e: e.score)
        worst_night = min(entries, key=lambda e: e.score)
        
        patterns_detected = []
        recommendations = []
        
        # Analyze caffeine
        caffeine_scores = [e.score for e in entries if e.caffeine_after_2pm]
        no_caffeine_scores = [e.score for e in entries if not e.caffeine_after_2pm]
        if caffeine_scores and no_caffeine_scores:
            avg_caf = sum(caffeine_scores) / len(caffeine_scores)
            avg_no_caf = sum(no_caffeine_scores) / len(no_caffeine_scores)
            diff = avg_no_caf - avg_caf
            if diff > 3:
                caffeine_impact = f"Late caffeine consumption correlates with a {diff:.1f} point drop in sleep score."
                patterns_detected.append("Caffeine after 2 PM impairs sleep quality.")
                recommendations.append("Limit caffeine intake to before 2:00 PM.")
            else:
                caffeine_impact = "No strong correlation detected between late caffeine and sleep scores."
        else:
            caffeine_impact = "Insufficient data to determine caffeine impact."
            
        # Analyze screen time
        screen_scores = [e.score for e in entries if e.screen_time_before_bed]
        no_screen_scores = [e.score for e in entries if not e.screen_time_before_bed]
        if screen_scores and no_screen_scores:
            avg_scr = sum(screen_scores) / len(screen_scores)
            avg_no_scr = sum(no_screen_scores) / len(no_screen_scores)
            diff = avg_no_scr - avg_scr
            if diff > 3:
                screen_time_impact = f"Pre-bed screen time correlates with a {diff:.1f} point drop in sleep score."
                patterns_detected.append("Blue light exposure before bed lowers sleep score.")
                recommendations.append("Implement a screen-free window 30-60 minutes before bedtime.")
            else:
                screen_time_impact = "No strong correlation detected between pre-bed screen time and sleep scores."
        else:
            screen_time_impact = "Insufficient data to determine screen time impact."
            
        # Analyze exercise
        exercise_scores = [e.score for e in entries if e.exercise_today]
        no_exercise_scores = [e.score for e in entries if not e.exercise_today]
        if exercise_scores and no_exercise_scores:
            avg_exe = sum(exercise_scores) / len(exercise_scores)
            avg_no_exe = sum(no_exercise_scores) / len(no_exercise_scores)
            diff = avg_exe - avg_no_exe
            if diff > 3:
                exercise_impact = f"Daytime exercise correlates with a {diff:.1f} point increase in sleep score."
                patterns_detected.append("Physical activity enhances overall sleep quality.")
                recommendations.append("Continue regular daily exercise to support rest.")
            else:
                exercise_impact = "No strong correlation detected between daily exercise and sleep scores."
        else:
            exercise_impact = "Insufficient data to determine exercise impact."
            
        if average_score < 50:
            verdict = VerdictLabel.NEEDS_ATTENTION
        elif average_score <= 65:
            verdict = VerdictLabel.IMPROVING
        elif average_score <= 80:
            verdict = VerdictLabel.ON_TRACK
        else:
            verdict = VerdictLabel.EXCELLENT
            
        if not patterns_detected:
            patterns_detected.append("Your sleep metrics are currently stable.")
        if not recommendations:
            recommendations.append("Maintain consistency in bedtime and waking hours.")
            
        analysis = SleepAnalysisSchema(
            user_id=user_id,
            period_days=days,
            average_score=round(average_score, 1),
            average_duration=round(average_duration, 1),
            average_wake_ups=round(average_wake_ups, 1),
            best_night=best_night,
            worst_night=worst_night,
            patterns_detected=patterns_detected,
            recommendations=recommendations,
            verdict=verdict,
            streak_days=streak_days,
            caffeine_impact=caffeine_impact,
            exercise_impact=exercise_impact,
            screen_time_impact=screen_time_impact
        )
        
        tool_response = MCPToolResponseSchema(
            tool_name="analyze_patterns",
            success=True,
            data={
                "analysis": analysis.model_dump(mode="json"),
                "entries": [e.model_dump(mode="json") for e in entries]
            },
            error=None,
            agent_next="ReporterAgent"
        )
        return tool_response.model_dump(mode="json")
        
    except Exception as e:
        logger.error("[MCP] Error in analyze_patterns: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="analyze_patterns",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


@mcp.tool()
def generate_report(user_id: str) -> dict:
    """
    Reporter Agent tool.
    Fetch last 7 days of sleep entries from SQLite.
    Generate Plotly bar chart:
    - X axis: dates
    - Y axis: sleep scores
    - Colors: red <50, amber 50-75, green >75
    Save chart as PNG to /tmp/restiq_report_{user_id}.png
    Build WeeklyReportSchema with analysis + chart path.
    Check milestones: 7, 14, 30, 60, 90 days.
    Return WeeklyReportSchema as dict wrapped in MCPToolResponseSchema.
    """
    logger.info("[MCP] generate_report called for user_id: %s", user_id)
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM sleep_entries 
        WHERE user_id = ? 
        ORDER BY date DESC LIMIT 7
        """, (user_id,))
        rows = cursor.fetchall()
        
        cursor.execute("SELECT total_entries, check_in_streak FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        total_entries = user_row[0] if user_row else 0
        check_in_streak = user_row[1] if user_row else 0
        conn.close()
        
        if not rows:
            raise ValueError(f"No sleep entries found to generate report for user {user_id}")
            
        rows_sorted = sorted(rows, key=lambda r: r["date"])
        dates = [r["date"] for r in rows_sorted]
        
        entries = []
        scores = []
        for r in rows_sorted:
            e_dict = dict(r)
            e_dict["caffeine_after_2pm"] = bool(e_dict["caffeine_after_2pm"])
            e_dict["exercise_today"] = bool(e_dict["exercise_today"])
            e_dict["screen_time_before_bed"] = bool(e_dict["screen_time_before_bed"])
            entry = SleepEntrySchema(**e_dict)
            if entry.score is None:
                entry.score = compute_sleep_score(entry)
            entries.append(entry)
            scores.append(entry.score)
            
        # Plotly chart generation
        import plotly.graph_objects as go
        import plotly.io as pio
        
        colors = []
        for s in scores:
            if s < 50:
                colors.append("#FF4B4B")  # red
            elif s <= 75:
                colors.append("#FFAA00")  # amber
            else:
                colors.append("#00CC88")  # green
                
        fig = go.Figure(data=[
            go.Bar(
                x=dates,
                y=scores,
                marker_color=colors,
                text=scores,
                textposition="auto",
            )
        ])
        fig.update_layout(
            title="Weekly Sleep Scores",
            xaxis_title="Date",
            yaxis_title="Sleep Score",
            yaxis=dict(range=[0, 100]),
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)"
        )
        
        chart_path = f"/tmp/restiq_report_{user_id}.png"
        os.makedirs(os.path.dirname(chart_path), exist_ok=True)
        try:
            pio.write_image(fig, chart_path, engine="kaleido")
        except Exception as e_img:
            logger.warning(
                "[MCP] Plotly write_image failed (kaleido not available): %s. Writing mock file.",
                str(e_img)
            )
            with open(chart_path, "wb") as f:
                f.write(b"MOCK_PNG_DATA")
                
        # Generate stats and analysis
        average_score = sum(scores) / len(scores)
        average_duration = sum(e.sleep_duration for e in entries) / len(entries)
        average_wake_ups = sum(e.wake_up_count for e in entries) / len(entries)
        
        best_night = max(entries, key=lambda e: e.score)
        worst_night = min(entries, key=lambda e: e.score)
        
        patterns_detected = []
        recommendations = []
        
        caffeine_scores = [e.score for e in entries if e.caffeine_after_2pm]
        no_caffeine_scores = [e.score for e in entries if not e.caffeine_after_2pm]
        if caffeine_scores and no_caffeine_scores:
            avg_caf = sum(caffeine_scores) / len(caffeine_scores)
            avg_no_caf = sum(no_caffeine_scores) / len(no_caffeine_scores)
            diff = avg_no_caf - avg_caf
            if diff > 3:
                caffeine_impact = f"Late caffeine consumption correlates with a {diff:.1f} point drop in sleep score."
                patterns_detected.append("Caffeine after 2 PM impairs sleep quality.")
                recommendations.append("Limit caffeine intake to before 2:00 PM.")
            else:
                caffeine_impact = "No strong correlation detected between late caffeine and sleep scores."
        else:
            caffeine_impact = "Insufficient data to determine caffeine impact."
            
        screen_scores = [e.score for e in entries if e.screen_time_before_bed]
        no_screen_scores = [e.score for e in entries if not e.screen_time_before_bed]
        if screen_scores and no_screen_scores:
            avg_scr = sum(screen_scores) / len(screen_scores)
            avg_no_scr = sum(no_screen_scores) / len(no_screen_scores)
            diff = avg_no_scr - avg_scr
            if diff > 3:
                screen_time_impact = f"Pre-bed screen time correlates with a {diff:.1f} point drop in sleep score."
                patterns_detected.append("Blue light exposure before bed lowers sleep score.")
                recommendations.append("Implement a screen-free window 30-60 minutes before bedtime.")
            else:
                screen_time_impact = "No strong correlation detected between pre-bed screen time and sleep scores."
        else:
            screen_time_impact = "Insufficient data to determine screen time impact."
            
        exercise_scores = [e.score for e in entries if e.exercise_today]
        no_exercise_scores = [e.score for e in entries if not e.exercise_today]
        if exercise_scores and no_exercise_scores:
            avg_exe = sum(exercise_scores) / len(exercise_scores)
            avg_no_exe = sum(no_exercise_scores) / len(no_exercise_scores)
            diff = avg_exe - avg_no_exe
            if diff > 3:
                exercise_impact = f"Daytime exercise correlates with a {diff:.1f} point increase in sleep score."
                patterns_detected.append("Physical activity enhances overall sleep quality.")
                recommendations.append("Continue regular daily exercise to support rest.")
            else:
                exercise_impact = "No strong correlation detected between daily exercise and sleep scores."
        else:
            exercise_impact = "Insufficient data to determine exercise impact."
            
        if average_score < 50:
            verdict = VerdictLabel.NEEDS_ATTENTION
        elif average_score <= 65:
            verdict = VerdictLabel.IMPROVING
        elif average_score <= 80:
            verdict = VerdictLabel.ON_TRACK
        else:
            verdict = VerdictLabel.EXCELLENT
            
        if not patterns_detected:
            patterns_detected.append("Your sleep metrics are currently stable.")
        if not recommendations:
            recommendations.append("Maintain consistency in bedtime and waking hours.")
            
        analysis = SleepAnalysisSchema(
            user_id=user_id,
            period_days=7,
            average_score=round(average_score, 1),
            average_duration=round(average_duration, 1),
            average_wake_ups=round(average_wake_ups, 1),
            best_night=best_night,
            worst_night=worst_night,
            patterns_detected=patterns_detected,
            recommendations=recommendations,
            verdict=verdict,
            streak_days=check_in_streak,
            caffeine_impact=caffeine_impact,
            exercise_impact=exercise_impact,
            screen_time_impact=screen_time_impact
        )
        
        # Check milestones: 7, 14, 30, 60, 90 days
        milestones = [7, 14, 30, 60, 90]
        milestone_message = None
        for m in milestones:
            if total_entries == m:
                milestone_message = f"Congratulations! You have logged {m} sleep entries. You've reached a major tracking milestone!"
                break
        if not milestone_message:
            for m in milestones:
                if check_in_streak == m:
                    milestone_message = f"Wow! You've achieved a check-in streak of {m} days. Incredible consistency!"
                    break
                    
        # Next week goal
        next_week_goal = "Aimed at improving sleep consistency: limit screen time 30 mins before sleep."
        if recommendations:
            next_week_goal = f"Focus on this recommendation: {recommendations[0]}"
            
        week_start = datetime.datetime.strptime(dates[0], "%Y-%m-%d").date()
        week_end = datetime.datetime.strptime(dates[-1], "%Y-%m-%d").date()
        
        report = WeeklyReportSchema(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            analysis=analysis,
            plotly_chart_path=chart_path,
            milestone_message=milestone_message,
            next_week_goal=next_week_goal
        )
        
        tool_response = MCPToolResponseSchema(
            tool_name="generate_report",
            success=True,
            data=report.model_dump(mode="json"),
            error=None,
            agent_next=None
        )
        return tool_response.model_dump(mode="json")
        
    except Exception as e:
        logger.error("[MCP] Error in generate_report: %s", str(e), exc_info=True)
        tool_response = MCPToolResponseSchema(
            tool_name="generate_report",
            success=False,
            data=None,
            error=str(e),
            agent_next=None
        )
        return tool_response.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()