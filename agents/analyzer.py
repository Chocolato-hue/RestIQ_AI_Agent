import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import datetime
from datetime import date
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("AnalyzerAgent")

# Import schemas and client helper
from schemas import (
    SleepEntrySchema,
    SleepAnalysisSchema,
    VerdictLabel
)
from tools import analyzer as analyzer_tool

class AnalyzerAgent:
    """
    AnalyzerAgent runs statistical and habit-based analysis on user sleep logs
    over a period, providing actionable recommendations and profile adaptations.
    """
    
    def analyze(self, user_id: str, days: int = 7) -> SleepAnalysisSchema:
        """
        Invokes the analyze_patterns MCP tool to generate a SleepAnalysisSchema.
        """
        logger.info("[ANALYZER] Analyzing last %d days for user_id '%s'", days, user_id)
        try:
            analysis, _entries = analyzer_tool.analyze_patterns(user_id, days)
            logger.info("[ANALYZER] Analysis complete. Verdict: %s, average score: %s", analysis.verdict.value, analysis.average_score)
            return analysis
        except Exception as e:
            logger.error("[ANALYZER] Exception occurred during analyze: %s", str(e), exc_info=True)
            raise ValueError(f"Analysis failed: {e}") from e

    def get_recommendation_message(self, analysis: SleepAnalysisSchema) -> str:
        """
        Builds a friendly, plain-language notification summarizing the sleep analysis results.
        """
        emoji_map = {
            VerdictLabel.NEEDS_ATTENTION: "🔴",
            VerdictLabel.IMPROVING: "🟡",
            VerdictLabel.ON_TRACK: "🟢",
            VerdictLabel.EXCELLENT: "⭐"
        }
        
        # Resolve emoji based on verdict (handling strings/enums safely)
        verdict_val = analysis.verdict
        if isinstance(verdict_val, str):
            try:
                verdict_val = VerdictLabel(verdict_val)
            except ValueError:
                pass
        emoji = emoji_map.get(verdict_val, "❓")
        
        patterns = "\n".join(f"- {p}" for p in analysis.patterns_detected)
        recs = "\n".join(f"- {r}" for r in analysis.recommendations)
        
        impacts = []
        if analysis.caffeine_impact:
            impacts.append(f"☕ Caffeine: {analysis.caffeine_impact}")
        if analysis.exercise_impact:
            impacts.append(f"🏃 Exercise: {analysis.exercise_impact}")
        if analysis.screen_time_impact:
            impacts.append(f"📱 Screen Time: {analysis.screen_time_impact}")
        impact_str = "\n".join(impacts)
        
        message = (
            f"📊 Your RestIQ Analysis\n\n"
            f"Sleep Score: {analysis.average_score}/100 {emoji}\n"
            f"Average Duration: {analysis.average_duration}h\n"
            f"Streak: {analysis.streak_days} days\n\n"
            f"What we found:\n{patterns}\n\n"
            f"What to improve:\n{recs}\n\n"
            f"{impact_str}\n\n"
            f"Next goal: Maintain consistency and limit late screen usage."
        )
        return message

    def check_adaptation(self, analysis: SleepAnalysisSchema, profile: dict) -> dict:
        """
        Evaluates sleep patterns against the user's profile to suggest configuration updates.
        """
        suggested_updates = {}
        signals = []
        
        # 1. Suggest updating caffeine sensitivity to HIGH if late caffeine has a negative impact
        if analysis.caffeine_impact and "drop" in analysis.caffeine_impact.lower():
            if profile.get("caffeine_sensitivity") != "HIGH":
                suggested_updates["caffeine_sensitivity"] = "HIGH"
                
        # 2. Check if the average score or verdict indicates improvement
        if analysis.verdict in [VerdictLabel.IMPROVING, VerdictLabel.ON_TRACK, VerdictLabel.EXCELLENT, "IMPROVING", "ON_TRACK", "EXCELLENT"]:
            signals.append("IMPROVING")
            
        # 3. Check if user streak is 7 days or more
        if analysis.streak_days >= 7:
            signals.append("MILESTONE_7_DAY_STREAK")
            
        return {
            "suggested_profile_updates": suggested_updates,
            "signals": signals
        }


def run_analyze(user_id: str, days: int = 7) -> SleepAnalysisSchema:
    """
    Convenience function to analyze user sleep patterns.
    """
    return AnalyzerAgent().analyze(user_id, days)


# Helper to seed data to ensure the manual test runs successfully
def seed_test_data(user_id: str):
    import sqlite3
    logger.info("[ANALYZER] Seeding database with test logs to verify analyzer functionality...")
    conn = sqlite3.connect("sleep_data.db")
    cursor = conn.cursor()
    
    # Create tables if not existing
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sleep_entries (
        user_id TEXT, date TEXT, bedtime TEXT, wake_time TEXT, sleep_duration REAL, wake_up_count INTEGER,
        sleep_quality TEXT, mood_on_wake TEXT, caffeine_after_2pm INTEGER, exercise_today INTEGER,
        screen_time_before_bed INTEGER, focus_level INTEGER, energy_level INTEGER, notes TEXT, score INTEGER,
        PRIMARY KEY (user_id, date)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY, username TEXT, target_wake_time TEXT, target_bedtime TEXT, target_sleep_duration REAL,
        caffeine_sensitivity TEXT, check_in_streak INTEGER, total_entries INTEGER,
        plan_status TEXT, plan_updated_at TEXT, created_at TEXT
    )
    """)
    
    cursor.execute("SELECT COUNT(*) FROM sleep_entries WHERE user_id = ?", (user_id,))
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT OR REPLACE INTO users (
            user_id, username, target_wake_time, target_bedtime, target_sleep_duration,
            caffeine_sensitivity, check_in_streak, total_entries, plan_status, plan_updated_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, "Test User", "07:00", "23:00", 8.0, "MEDIUM", 7, 7, "INSUFFICIENT_DATA", None, datetime.datetime.now().isoformat()))
        
        # Seed 7 days of sleep logs, making caffeine nights correlate with low scores
        for i in range(7):
            log_date = date.today() - datetime.timedelta(days=i)
            has_caffeine = (i % 2 == 0)
            score = 45 if has_caffeine else 85
            
            cursor.execute("""
            INSERT OR REPLACE INTO sleep_entries (
                user_id, date, bedtime, wake_time, sleep_duration, wake_up_count,
                sleep_quality, mood_on_wake, caffeine_after_2pm, exercise_today,
                screen_time_before_bed, focus_level, energy_level, notes, score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                log_date.isoformat(),
                "23:30" if has_caffeine else "22:30",
                "07:00",
                7.5 if has_caffeine else 8.5,
                3 if has_caffeine else 0,
                "FAIR" if has_caffeine else "EXCELLENT",
                "TIRED" if has_caffeine else "GREAT",
                1 if has_caffeine else 0,
                0 if has_caffeine else 1,
                1 if has_caffeine else 0,
                2 if has_caffeine else 4,
                2 if has_caffeine else 4,
                "Seeded test log.",
                score
            ))
        conn.commit()
    conn.close()


if __name__ == "__main__":
    user_id = "analyzer_manual_test_user"
    seed_test_data(user_id)
    
    agent = AnalyzerAgent()
    
    print("\n--- AnalyzerAgent Manual Test ---")
    try:
        # Test 1: run_analyze
        print(f"\n[Test 1] Running sleep analysis for '{user_id}'...")
        analysis = run_analyze(user_id, days=7)
        print("Analysis successfully generated.")
        
        # Test 2: print recommendation message
        print("\n[Test 2] Printing generated recommendation message...")
        rec_msg = agent.get_recommendation_message(analysis)
        print(rec_msg)
        
        # Test 3: print adaptation suggestions
        print("\n[Test 3] Printing user profile adaptation suggestions...")
        mock_profile = {
            "user_id": user_id,
            "username": "Test User",
            "caffeine_sensitivity": "MEDIUM"
        }
        adaptations = agent.check_adaptation(analysis, mock_profile)
        print(json.dumps(adaptations, indent=2))
        
    except Exception as err:
        print(f"\nTest failed with error: {err}")