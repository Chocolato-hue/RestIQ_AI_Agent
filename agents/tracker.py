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
logger = logging.getLogger("TrackerAgent")

# Import schemas and client helper
from schemas import SleepEntrySchema, MCPToolResponseSchema, SleepQuality, MoodOnWake
from mcp_client import get

class TrackerAgent:
    """
    TrackerAgent handles saving sleep logs, retrieving historical entries,
    obtaining the most recent entry, and calculating user streaks.
    """
    
    def store(self, entry: SleepEntrySchema) -> bool:
        """
        Saves a SleepEntrySchema to the database via the store_sleep_data MCP tool.
        """
        logger.info("[TRACKER] Storing entry for user_id '%s' and date '%s'", entry.user_id, entry.date)
        try:
            response_dict = get("store_sleep_data", {"entry": entry.model_dump(mode="json")})
            tool_response = MCPToolResponseSchema(**response_dict)
            
            if tool_response.success:
                logger.info("[TRACKER] Entry saved successfully.")
                return True
            else:
                logger.error("[TRACKER] Failed to save entry: %s", tool_response.error or "Unknown error")
                return False
        except Exception as e:
            logger.error("[TRACKER] Exception occurred while storing entry: %s", str(e), exc_info=True)
            return False

    def get_history(self, user_id: str, days: int = 7) -> list[SleepEntrySchema]:
        """
        Retrieves sleep log history for a user over the past N days.
        Reuses the analyze_patterns MCP tool, which contains the list of entries in its payload.
        """
        logger.info("[TRACKER] Fetching last %d days for user_id '%s'", days, user_id)
        try:
            response_dict = get("analyze_patterns", {"user_id": user_id, "days": days})
            tool_response = MCPToolResponseSchema(**response_dict)
            
            if tool_response.success and tool_response.data and "entries" in tool_response.data:
                raw_entries = tool_response.data["entries"]
                entries = [SleepEntrySchema(**e) for e in raw_entries]
                logger.info("[TRACKER] Found %d entries.", len(entries))
                return entries
            else:
                logger.warning("[TRACKER] Failed to fetch history or no entries found: %s", tool_response.error or "No data")
                return []
        except Exception as e:
            logger.error("[TRACKER] Exception occurred while fetching history: %s", str(e), exc_info=True)
            return []

    def get_latest(self, user_id: str) -> SleepEntrySchema | None:
        """
        Retrieves the user's most recent sleep entry.
        """
        logger.info("[TRACKER] Fetching latest entry for user_id '%s'", user_id)
        history = self.get_history(user_id, days=1)
        if history:
            logger.info("[TRACKER] Latest entry found for date '%s'.", history[0].date)
            return history[0]
        else:
            logger.info("[TRACKER] No entry found.")
            return None

    def get_streak(self, user_id: str) -> int:
        """
        Calculates consecutive day check-in streak counting backwards from today.
        """
        logger.info("[TRACKER] Calculating streak for user_id '%s'", user_id)
        entries = self.get_history(user_id, days=90)
        
        # Map dates to a set of date objects for efficient lookup
        logged_dates = set()
        for e in entries:
            if isinstance(e.date, date):
                logged_dates.add(e.date)
            else:
                logged_dates.add(datetime.datetime.strptime(str(e.date), "%Y-%m-%d").date())
        
        streak = 0
        current_check_date = date.today()
        
        # If the user hasn't logged today yet, check yesterday to continue the streak
        if current_check_date not in logged_dates:
            current_check_date -= datetime.timedelta(days=1)
            
        while current_check_date in logged_dates:
            streak += 1
            current_check_date -= datetime.timedelta(days=1)
            
        logger.info("[TRACKER] Streak = %d days.", streak)
        return streak


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────────────────────────────────────

def run_store(entry: SleepEntrySchema) -> bool:
    """Convenience function to store a sleep log entry."""
    return TrackerAgent().store(entry)


def run_get_history(user_id: str, days: int) -> list[SleepEntrySchema]:
    """Convenience function to retrieve sleep log history."""
    return TrackerAgent().get_history(user_id, days)


def run_get_latest(user_id: str) -> SleepEntrySchema | None:
    """Convenience function to retrieve the latest sleep log entry."""
    return TrackerAgent().get_latest(user_id)


if __name__ == "__main__":
    agent = TrackerAgent()
    user_id = "tracker_manual_test_user"
    
    print("\n--- TrackerAgent Manual Test ---")
    
    # 1. Create a mock entry for today
    mock_entry = SleepEntrySchema(
        user_id=user_id,
        date=date.today(),
        bedtime="23:30",
        wake_time="07:30",
        sleep_duration=8.0,
        wake_up_count=1,
        sleep_quality=SleepQuality.GOOD,
        mood_on_wake=MoodOnWake.GOOD,
        caffeine_after_2pm=False,
        exercise_today=True,
        screen_time_before_bed=False,
        focus_level=4,
        energy_level=4,
        notes="Spent time reading a book before bed.",
        score=None
    )
    
    # 2. Test store()
    print("\n[Test 1] Storing mock sleep entry for today...")
    store_success = agent.store(mock_entry)
    print(f"Store Success: {store_success}")
    
    # 3. Test get_history(days=7)
    print("\n[Test 2] Fetching history (7 days)...")
    history = agent.get_history(user_id, days=7)
    print(f"Found {len(history)} entries in history.")
    for idx, e in enumerate(history, 1):
        print(f"  Entry {idx}: date={e.date}, score={e.score}, duration={e.sleep_duration}")
        
    # 4. Test get_latest()
    print("\n[Test 3] Fetching latest entry...")
    latest = agent.get_latest(user_id)
    if latest:
        print(f"Latest entry date: {latest.date}")
        print(f"Latest entry details: bedtime={latest.bedtime}, wake_time={latest.wake_time}, score={latest.score}")
    else:
        print("No latest entry found.")
        
    # 5. Test get_streak()
    print("\n[Test 4] Fetching current streak...")
    streak = agent.get_streak(user_id)
    print(f"Current Streak: {streak} days")