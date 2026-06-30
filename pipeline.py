import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import logging
import json
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import loggers
from logger_config import get_pipeline_logger
logger = get_pipeline_logger()

from sleep_coach import generate_coaching, format_coaching_message
from agents.tracker import run_get_history
# Import agent convenience functions
from agents.intake import run_intake
from agents.scheduler import run_circadian, run_smart_followup, run_evaluate_plan, SchedulerAgent
from agents.tracker import run_store, run_get_latest, run_get_history
from agents.analyzer import run_analyze
from agents.reporter import run_generate, ReporterAgent

# Import all schemas
from schemas import (
    SleepEntrySchema,
    UserProfileSchema,
    CircadianSchema,
    SmartFollowUpSchema,
    SleepAnalysisSchema,
    WeeklyReportSchema,
    MCPToolResponseSchema,
    PlanAdjustmentSchema,
    SleepQuality,
    MoodOnWake,
    VerdictLabel,
    CaffeineSensitivity
)

from services.scoring import compute_sleep_score

class RestIQPipeline:
    """
    RestIQPipeline coordinates the execution flow between Intake, Scheduler,
    Tracker, Analyzer, and Reporter agents.
    """
    
    def handle_checkin(self, user_id: str, raw_text: str) -> dict:
        """
        Processes a user's daily check-in reply.
        Classifies habits, saves sleep log, updates stats/streaks, calculates
        circadian sleep windows, runs periodic analysis, and returns a summary message.
        """
        logger.info("[PIPELINE] Handling check-in for user_id '%s'", user_id)
        
        # 1. Run intake agent to extract raw text into structured schema
        entry: SleepEntrySchema = run_intake(user_id, raw_text)
        
        # 2. Run tracker agent to store the entry in SQLite and update stats
        store_success = run_store(entry)
        if not store_success:
            logger.warning("[PIPELINE] Tracker failed to store the sleep entry in database.")
            
        # Compute sleep score for the logged night (runs local score calculation)
        score_val = compute_sleep_score(entry)
        entry.score = score_val
        
        # 3. Run circadian calculations (defaulting to wake time logged, or "07:00")
        wake_time = entry.wake_time if entry.wake_time else "07:00"
        circadian: CircadianSchema = run_circadian(wake_time=wake_time, sleep_duration=8.0)
        
        # 4. Evaluate the adaptive plan (daily path: reports trend, only a
        # streak override can commit a change — the weekly trend itself does
        # not move the target on a daily check-in).
        plan_adjustment: PlanAdjustmentSchema = run_evaluate_plan(user_id, commit_weekly_adjustment=False)
        
        # 5. Run analyzer for the last 7 days of sleep metrics
        analysis: SleepAnalysisSchema = run_analyze(user_id, days=7)
        
        # 6. Get history for sleep debt calculation
        history = run_get_history(user_id, days=7)
        
        # 7. Generate science-based coaching
        from sleep_coach import generate_coaching, format_coaching_message
        coaching = generate_coaching(
            entry=entry,
            history=history,
            analysis=analysis,
            target_wake_time=entry.wake_time or "07:00",
        )
        
        # 8. Format the reply
        coaching_text = format_coaching_message(coaching)
        
        reply_message = (
            f"✅ *Sleep logged!*\n"
            f"Score: {score_val}/100 · Duration: {entry.sleep_duration}h\n\n"
            f"{coaching_text}"
        )
        
        # If the plan was adjusted (only possible here via a streak override),
        # surface that to the user immediately rather than waiting for the
        # weekly report.
        if plan_adjustment.adjusted:
            reply_message += f"\n\n📋 *Plan update:* {plan_adjustment.reason}"
        
        logger.info("[PIPELINE] Check-in complete, score: %d", score_val)
        
        return {
            "entry": entry,
            "circadian": circadian,
            "plan_adjustment": plan_adjustment,
            "analysis": analysis,
            "reply_message": reply_message
        }

    def handle_weekly_report(self, user_id: str) -> dict:
        """
        Generates a comprehensive weekly report containing scores analysis,
        milestone evaluations, coaching recommendations, and Plotly visualization.
        Also evaluates the adaptive plan with commit_weekly_adjustment=True,
        so a confirmed weekly trend (improving or declining) is allowed to
        shift the user's target bedtime going into the next week.
        """
        logger.info("[PIPELINE] Generating weekly report for user_id '%s'", user_id)
        
        # 1. Run reporter agent to generate weekly report card and chart
        report: WeeklyReportSchema = run_generate(user_id)
        
        # 2. Run analyzer agent to get sleep analysis
        analysis: SleepAnalysisSchema = run_analyze(user_id, days=7)
        
        # 3. Evaluate the adaptive plan, committing any trend-based adjustment
        plan_adjustment: PlanAdjustmentSchema = run_evaluate_plan(user_id, commit_weekly_adjustment=True)
        
        # 4. Format Telegram message, appending the plan update if relevant
        telegram_message = ReporterAgent().format_telegram_message(report)
        if plan_adjustment.triggered_by.value != "NONE":
            telegram_message += f"\n\n📋 Plan update: {plan_adjustment.reason}"
        
        logger.info("[PIPELINE] Weekly report complete for user_id '%s'", user_id)
        
        return {
            "report": report,
            "analysis": analysis,
            "plan_adjustment": plan_adjustment,
            "telegram_message": telegram_message,
            "chart_path": report.plotly_chart_path
        }

    def handle_daily_prompt(self, user_id: str, latest_entry: SleepEntrySchema = None) -> str:
        """
        Generates the daily check-in prompt containing either core questions
        or smart follow-up questions customized to previous sleep logs.
        """
        logger.info("[PIPELINE] Generating daily prompt for user_id '%s'", user_id)
        scheduler = SchedulerAgent()
        prompt = scheduler.send_daily_checkin(bot=None, user_id=user_id, chat_id="", latest_entry=latest_entry)
        return prompt


# ──────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ──────────────────────────────────────────────────────────────────────────────

def run_checkin(user_id: str, raw_text: str) -> dict:
    return RestIQPipeline().handle_checkin(user_id, raw_text)


def run_weekly_report(user_id: str) -> dict:
    return RestIQPipeline().handle_weekly_report(user_id)


def run_daily_prompt(user_id: str, latest_entry: SleepEntrySchema = None) -> str:
    return RestIQPipeline().handle_daily_prompt(user_id, latest_entry)


if __name__ == "__main__":
    from agents.analyzer import seed_test_data
    
    test_user = "pipeline_test_user"
    
    print("\n--- RestIQPipeline Manual Test ---")
    
    # Seed data
    seed_test_data(test_user)
    pipeline = RestIQPipeline()
    
    # Test 1: handle_daily_prompt
    print("\n[Test 1] Generating daily prompt (without history)...")
    prompt_no_hist = pipeline.handle_daily_prompt(test_user, latest_entry=None)
    print(prompt_no_hist)
    
    # Fetch latest entry to run with history
    latest_log = run_get_latest(test_user)
    print("\n[Test 1b] Generating daily prompt (with history)...")
    prompt_hist = pipeline.handle_daily_prompt(test_user, latest_entry=latest_log)
    print(prompt_hist)
    
    # Test 2: handle_checkin with sample text
    sample_text = (
        "I went to bed at 11pm, woke up at 7am, "
        "woke up once during night, slept pretty well, "
        "feeling good this morning, no caffeine after 2, "
        "did a quick workout, had my phone before bed"
    )
    print("\n[Test 2] Handling daily check-in...")
    checkin_res = pipeline.handle_checkin(test_user, sample_text)
    print("Reply Message:")
    print(checkin_res["reply_message"])
    
    # Test 3: handle_weekly_report
    print("\n[Test 3] Generating weekly report...")
    report_res = pipeline.handle_weekly_report(test_user)
    print("Telegram Message:")
    print(report_res["telegram_message"])
    print("Chart Path:", report_res["chart_path"])