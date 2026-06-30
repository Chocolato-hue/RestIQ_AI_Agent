import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import datetime
import pathlib
from datetime import date
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ReporterAgent")

# Import schemas and enums
from schemas import (
    WeeklyReportSchema,
    SleepAnalysisSchema,
    VerdictLabel
)
from services import reporting as reporting_service

class ReporterAgent:
    """
    ReporterAgent handles weekly sleep reports generation, formatting for Telegram,
    and dispatching messages (with visual charts) to Telegram users.
    """
    
    def generate(self, user_id: str) -> WeeklyReportSchema:
        """
        Invokes the generate_report MCP tool to construct a WeeklyReportSchema for the user.
        """
        logger.info("[REPORTER] Generating weekly report for user_id '%s'", user_id)
        try:
            report = reporting_service.generate_report(user_id)
            logger.info("[REPORTER] Report generated, chart saved at path: %s", report.plotly_chart_path)
            return report
                
        except Exception as e:
            logger.error("[REPORTER] Exception occurred during report generation: %s", str(e), exc_info=True)
            raise ValueError(f"Report generation failed: {e}") from e

    def format_telegram_message(self, report: WeeklyReportSchema) -> str:
        """
        Formats the weekly sleep report data into a beautiful and readable Telegram message.
        """
        analysis = report.analysis
        
        emoji_map = {
            VerdictLabel.NEEDS_ATTENTION: "🔴",
            VerdictLabel.IMPROVING: "🟡",
            VerdictLabel.ON_TRACK: "🟢",
            VerdictLabel.EXCELLENT: "⭐"
        }
        
        verdict_val = analysis.verdict
        if isinstance(verdict_val, str):
            try:
                verdict_val = VerdictLabel(verdict_val)
            except ValueError:
                pass
        emoji = emoji_map.get(verdict_val, "❓")
        
        patterns = "\n".join(f"- {p}" for p in analysis.patterns_detected)
        
        best_date = analysis.best_night.date if analysis.best_night else "N/A"
        best_score = analysis.best_night.score if analysis.best_night else 0
        worst_date = analysis.worst_night.date if analysis.worst_night else "N/A"
        worst_score = analysis.worst_night.score if analysis.worst_night else 0
        
        milestone = f"\n{report.milestone_message}" if report.milestone_message else ""
        
        message = (
            f"🌙 RestIQ Weekly Report\n"
            f"{report.week_start} → {report.week_end}\n\n"
            f"Sleep Score: {analysis.average_score}/100 {emoji}\n"
            f"Avg Duration: {analysis.average_duration}h\n"
            f"Avg Wake-ups: {analysis.average_wake_ups}\n"
            f"Streak: {analysis.streak_days} days 🔥\n\n"
            f"Best night: {best_date} ({best_score}/100)\n"
            f"Worst night: {worst_date} ({worst_score}/100)\n\n"
            f"Key insights:\n{patterns}\n\n"
            f"Your goal next week:\n{report.next_week_goal}\n"
            f"{milestone}"
        )
        return message

    def send_to_telegram(self, bot, chat_id: str, report: WeeklyReportSchema) -> bool:
        """
        Dispatches the formatted weekly report to the user on Telegram.
        Sends the plotly chart image if it exists, followed by the text summary.
        Supports both synchronous and asynchronous telegram bot implementations.
        """
        logger.info("[REPORTER] Sending report to chat_id '%s'", chat_id)
        try:
            message_text = self.format_telegram_message(report)
            chart_path = report.plotly_chart_path
            has_chart = chart_path and os.path.exists(chart_path)
            
            import inspect
            import asyncio
            
            async def do_send():
                if has_chart:
                    with open(chart_path, "rb") as photo:
                        if inspect.iscoroutinefunction(bot.send_photo):
                            await bot.send_photo(chat_id=chat_id, photo=photo)
                        else:
                            bot.send_photo(chat_id=chat_id, photo=photo)
                    
                    if inspect.iscoroutinefunction(bot.send_message):
                        await bot.send_message(chat_id=chat_id, text=message_text)
                    else:
                        bot.send_message(chat_id=chat_id, text=message_text)
                else:
                    if inspect.iscoroutinefunction(bot.send_message):
                        await bot.send_message(chat_id=chat_id, text=message_text)
                    else:
                        bot.send_message(chat_id=chat_id, text=message_text)
            
            # Invoke sending process
            is_async_message = inspect.iscoroutinefunction(bot.send_message)
            is_async_photo = has_chart and inspect.iscoroutinefunction(bot.send_photo)
            
            if is_async_message or is_async_photo:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Inside running event loop (e.g. in async framework), schedule task
                        asyncio.run_coroutine_threadsafe(do_send(), loop).result()
                    else:
                        loop.run_until_complete(do_send())
                except RuntimeError:
                    # No active event loop in this thread, use run()
                    asyncio.run(do_send())
            else:
                # Fully synchronous fallback
                if has_chart:
                    with open(chart_path, "rb") as photo:
                        bot.send_photo(chat_id=chat_id, photo=photo)
                    bot.send_message(chat_id=chat_id, text=message_text)
                else:
                    bot.send_message(chat_id=chat_id, text=message_text)
                    
            logger.info("[REPORTER] Report sent successfully.")
            return True
            
        except Exception as e:
            logger.error("[REPORTER] Report sending failed: %s", str(e), exc_info=True)
            return False


def run_generate(user_id: str) -> WeeklyReportSchema:
    """
    Convenience function to generate a weekly report.
    """
    return ReporterAgent().generate(user_id)


if __name__ == "__main__":
    from analyzer import seed_test_data
    
    test_user = "reporter_test_user"
    seed_test_data(test_user)
    
    agent = ReporterAgent()
    
    print("\n--- ReporterAgent Manual Test ---")
    try:
        # 1. Test generate()
        print(f"\n[Test 1] Generating weekly report for user '{test_user}'...")
        report = run_generate(test_user)
        print("Weekly report successfully generated.")
        
        # 2. Test format_telegram_message()
        print("\n[Test 2] Printing formatted Telegram message summary...")
        telegram_msg = agent.format_telegram_message(report)
        print(telegram_msg)
        
        # 3. Test chart path
        print("\n[Test 3] Plotly sleep chart saved at:")
        print(f"  {report.plotly_chart_path}")
        if os.path.exists(report.plotly_chart_path):
            print("  ✔ Chart file exists on disk!")
        else:
            print("  ✖ Chart file missing on disk!")
            
    except Exception as err:
        print(f"\nTest failed with error: {err}")
