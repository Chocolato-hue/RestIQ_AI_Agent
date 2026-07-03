import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import datetime
from datetime import date
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("SchedulerAgent")

# Import schemas and enums
from schemas import (
    SleepEntrySchema,
    CircadianSchema,
    SmartFollowUpSchema,
    UserProfileSchema,
    PlanAdjustmentSchema,
    SleepQuality,
    MoodOnWake
)
from tools import circadian as circadian_tool
from tools import plan as plan_tool

class SchedulerAgent:
    """
    SchedulerAgent manages sleep schedule recommendations and generates personalized,
    pattern-based check-in questions for the user.
    """
    
    def get_circadian(self, wake_time: str, sleep_duration: float = 8.0) -> CircadianSchema:
        """
        Calculates recommended bedtime and wind-down periods using the circadian calculator MCP tool.
        """
        logger.info("[SCHEDULER] Calculating circadian recommendations for wake_time='%s', duration=%s", wake_time, sleep_duration)
        try:
            return circadian_tool.calculate_circadian(wake_time, sleep_duration)
                
        except Exception as e:
            logger.error("[SCHEDULER] Error during circadian calculation: %s", str(e), exc_info=True)
            raise ValueError(f"Circadian calculation failed: {e}") from e

    def evaluate_and_adjust_plan(self, user_id: str, commit_weekly_adjustment: bool = False) -> PlanAdjustmentSchema:
        """
        Evaluates the user's adaptive sleep plan via the evaluate_plan MCP tool
        and returns the resulting decision (whether the plan changed, why, and
        the new target bedtime if applicable).

        commit_weekly_adjustment=False (default): used on the daily check-in
        path. The rolling trend is still computed and returned for status
        purposes, but only a streak override can actually commit a change —
        this avoids nudging the user's plan every single day.

        commit_weekly_adjustment=True: used on the weekly report path. A
        confirmed IMPROVING/DECLINING trend is allowed to commit a target
        bedtime shift.
        """
        logger.info(
            "[SCHEDULER] Evaluating adaptive plan for user_id '%s' (commit_weekly_adjustment=%s)",
            user_id, commit_weekly_adjustment
        )
        try:
            return plan_tool.evaluate_plan(user_id, commit_weekly_adjustment)

        except Exception as e:
            logger.error("[SCHEDULER] Error during plan evaluation: %s", str(e), exc_info=True)
            raise ValueError(f"Plan evaluation failed: {e}") from e

    def get_smart_followup(self, user_id: str, latest_entry: SleepEntrySchema) -> SmartFollowUpSchema:
        """
        Generates standard core check-in questions combined with custom conditional follow-up
        questions based on patterns detected in the user's latest sleep log.
        """
        logger.info("[SCHEDULER] Generating smart follow-up questions for user_id '%s'", user_id)
        
        core_questions = [
            "What time did you go to sleep and wake up?",
            "How many times did you wake up?",
            "How do you feel right now on a scale of 1-10?"
        ]
        
        followup_questions = []
        triggered_by = []
        
        # Rule 1: Caffeine impact
        if latest_entry.score is not None and latest_entry.score < 50 and latest_entry.caffeine_after_2pm:
            followup_questions.append("Did you skip caffeine after 2pm today?")
            triggered_by.append("Low score correlated with late caffeine")
            
        # Rule 2: Water intake / Wake ups
        if latest_entry.wake_up_count > 2:
            followup_questions.append("Did you drink water close to bedtime?")
            triggered_by.append("High wake-up count detected")
            
        # Rule 3: Morning tiredness / Mood
        if latest_entry.mood_on_wake in ["TERRIBLE", "TIRED", MoodOnWake.TERRIBLE, MoodOnWake.TIRED]:
            followup_questions.append("What is one thing you could do differently tonight?")
            triggered_by.append("Poor morning mood detected")
            
        # Rule 4: Screens before bed
        if latest_entry.screen_time_before_bed:
            followup_questions.append("Did you avoid screens before bed last night?")
            triggered_by.append("Screen time before bed detected")
            
        # Slice to ensure maximum of 3 triggered questions
        followup_questions = followup_questions[:3]
        triggered_by = triggered_by[:3]
        
        return SmartFollowUpSchema(
            user_id=user_id,
            date=date.today(),
            core_questions=core_questions,
            followup_questions=followup_questions,
            triggered_by=triggered_by
        )

    def build_session_context(self, latest_entry: SleepEntrySchema = None) -> Optional[str]:
        """Build a short context hint for the concierge opener from prior sleep data."""
        if not latest_entry:
            return None

        hints = []
        if latest_entry.score is not None and latest_entry.score < 60:
            hints.append(f"yesterday's score was {latest_entry.score}")
        if latest_entry.screen_time_before_bed:
            hints.append("late screens may have played a role")
        if latest_entry.caffeine_after_2pm:
            hints.append("late caffeine was a factor")
        if latest_entry.wake_up_count > 2:
            hints.append("you had several wake-ups")
        if latest_entry.sleep_duration < 7:
            hints.append("sleep was under 7 hours")

        if not hints:
            if latest_entry.score and latest_entry.score >= 85:
                return "You had a great sleep score yesterday — let's keep the momentum."
            return None

        return "Yesterday " + ", and ".join(hints[:2]) + "."

    def send_daily_checkin(self, bot, user_id: str, chat_id: str, latest_entry: SleepEntrySchema = None) -> str:
        """
        Returns a single conversational opener for the concierge check-in.
        """
        logger.info("[SCHEDULER] Sending daily check-in message to user_id '%s'", user_id)

        context = self.build_session_context(latest_entry)
        if context:
            return f"🌙 Good morning! {context.capitalize()} How did you sleep last night?"
        return "🌙 Good morning! How did you sleep last night?"


def run_circadian(wake_time: str, sleep_duration: float = 8.0) -> CircadianSchema:
    """
    Convenience function to calculate recommended circadian schedule.
    """
    agent = SchedulerAgent()
    return agent.get_circadian(wake_time, sleep_duration)


def run_smart_followup(user_id: str, latest_entry: SleepEntrySchema) -> SmartFollowUpSchema:
    """
    Convenience function to get smart follow-up questions.
    """
    agent = SchedulerAgent()
    return agent.get_smart_followup(user_id, latest_entry)


def run_evaluate_plan(user_id: str, commit_weekly_adjustment: bool = False) -> PlanAdjustmentSchema:
    """
    Convenience function to evaluate and (conditionally) adjust the user's plan.
    """
    agent = SchedulerAgent()
    return agent.evaluate_and_adjust_plan(user_id, commit_weekly_adjustment)


if __name__ == "__main__":
    agent = SchedulerAgent()
    
    print("\n--- SchedulerAgent Manual Test ---")
    
    # Test 1: get_circadian("07:00", 8.0)
    print("\n[Test 1] Calculating circadian recommendations for wake time '07:00' with 8.0 hours duration...")
    try:
        circadian_res = agent.get_circadian("07:00", 8.0)
        print("Recommended Bedtime:", circadian_res.recommended_bedtime)
        print("Wind Down Start:", circadian_res.wind_down_start)
        print("Circadian Schema JSON:")
        print(circadian_res.model_dump_json(indent=2))
    except Exception as err:
        print(f"Test 1 failed with error: {err}")
        
    # Test 2: get_smart_followup with a mock SleepEntrySchema
    print("\n[Test 2] Generating smart follow-ups from mock SleepEntrySchema...")
    mock_entry = SleepEntrySchema(
        user_id="test_user_123",
        date=date.today(),
        bedtime="23:00",
        wake_time="07:00",
        sleep_duration=8.0,
        wake_up_count=3,
        sleep_quality=SleepQuality.FAIR,
        mood_on_wake=MoodOnWake.TIRED,
        caffeine_after_2pm=True,
        exercise_today=False,
        screen_time_before_bed=True,
        focus_level=2,
        energy_level=2,
        notes="Mock note.",
        score=45
    )
    
    try:
        followup_res = agent.get_smart_followup(user_id="test_user_123", latest_entry=mock_entry)
        print("Triggered By:", followup_res.triggered_by)
        print("Follow-up Questions:", followup_res.followup_questions)
        print("Daily Check-in Message Preview:")
        msg_preview = agent.send_daily_checkin(bot=None, user_id="test_user_123", chat_id="mock_chat_id", latest_entry=mock_entry)
        print(msg_preview)
    except Exception as err:
        print(f"Test 2 failed with error: {err}")

    # Test 3: evaluate_and_adjust_plan (daily, non-committing path)
    print("\n[Test 3] Evaluating adaptive plan (daily path, no commit)...")
    try:
        plan_res = agent.evaluate_and_adjust_plan(user_id="test_user_123", commit_weekly_adjustment=False)
        print("Status:", plan_res.status.value)
        print("Triggered By:", plan_res.triggered_by.value)
        print("Adjusted:", plan_res.adjusted)
        print("Reason:", plan_res.reason)
    except Exception as err:
        print(f"Test 3 failed with error: {err}")