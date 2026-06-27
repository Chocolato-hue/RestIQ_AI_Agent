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
    SleepQuality,
    MoodOnWake,
    VerdictLabel,
    CaffeineSensitivity
)

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
        target_sleep_duration REAL,
        caffeine_sensitivity TEXT,
        check_in_streak INTEGER,
        total_entries INTEGER,
        created_at TEXT
    )
    """)
    
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
def parse_sleep_input(user_id: str, raw_text: str) -> dict:
    """
    Intake Agent tool.
    Parse natural language sleep input into structured SleepEntrySchema.
    Use Gemini to extract: bedtime, wake_time, wake_up_count,
    sleep_quality, mood_on_wake, caffeine_after_2pm,
    exercise_today, screen_time_before_bed, notes.
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
    Validate entry as SleepEntrySchema.
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
            screen_time_before_bed, notes, score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                user_id, username, target_wake_time, target_sleep_duration,
                caffeine_sensitivity, check_in_streak, total_entries, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                validated.user_id,
                f"User_{validated.user_id}",
                "07:00",
                8.0,
                "MEDIUM",
                1,
                1,
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
