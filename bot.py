import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import asyncio
import datetime
import sqlite3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import loggers
from logger_config import get_bot_logger
logger = get_bot_logger()

# Import telegram dependencies
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# Import pipeline and tracker functions
from pipeline import run_checkin, run_weekly_report, run_daily_prompt
from agents.tracker import run_get_latest

# ──────────────────────────────────────────────────────────────────────────────
# Async Handlers
# ──────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends the welcome message and command overview to new users.
    """
    username = update.effective_user.username or update.effective_user.first_name
    logger.info("[BOT] New user started: %s", username)
    welcome_text = (
        "👋 Welcome to RestIQ — your personal sleep concierge!\n\n"
        "I'll check in with you every morning to track your sleep.\n"
        "Each week you'll get a visual report with insights.\n\n"
        "Commands:\n"
        "/checkin — log your sleep now\n"
        "/report — get your weekly sleep report\n"
        "/help — show this message\n\n"
        "Or just reply naturally to my morning check-in!"
    )
    await update.message.reply_text(welcome_text)


async def handle_checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Initiates the check-in command. Sets user state awaiting_checkin to True.
    """
    user_id = str(update.effective_user.id)
    logger.info("[BOT] Awaiting check-in from user_id: %s", user_id)
    await update.message.reply_text("🌙 Tell me about last night's sleep...")
    context.user_data["awaiting_checkin"] = True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles standard incoming text messages. If awaiting_checkin, runs the
    RestIQ check-in pipeline. Otherwise, displays the daily check-in questions.
    """
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    message_text = update.message.text
    logger.info("[BOT] Message received from %s", username)

    if context.user_data.get("awaiting_checkin"):
        await update.message.reply_text("⏳ Analyzing your sleep...")
        try:
            # Execute synchronous check-in pipeline in a separate thread to avoid blocking loop
            checkin_res = await asyncio.to_thread(run_checkin, user_id, message_text)
            reply_message = checkin_res["reply_message"]
            score = checkin_res["entry"].score
            
            await update.message.reply_text(reply_message)
            context.user_data["awaiting_checkin"] = False
            logger.info("[BOT] Check-in complete, score: %s", score)
        except Exception as e:
            logger.error("[BOT] Error during run_checkin execution: %s", str(e), exc_info=True)
            await update.message.reply_text(f"❌ Oops, I had trouble parsing that check-in: {e}")
    else:
        try:
            # Retrieve latest entry and daily prompt
            latest_entry = await asyncio.to_thread(run_get_latest, user_id)
            prompt = await asyncio.to_thread(run_daily_prompt, user_id, latest_entry)
            
            await update.message.reply_text(prompt)
            context.user_data["awaiting_checkin"] = True
        except Exception as e:
            logger.error("[BOT] Error generating daily check-in prompt: %s", str(e), exc_info=True)
            await update.message.reply_text(f"❌ Error starting check-in sequence: {e}")


async def handle_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Generates and dispatches the weekly report and plotly chart.
    """
    user_id = str(update.effective_user.id)
    await update.message.reply_text("📊 Generating your weekly report...")
    try:
        # Execute synchronous weekly report pipeline in a separate thread
        report_res = await asyncio.to_thread(run_weekly_report, user_id)
        telegram_message = report_res["telegram_message"]
        chart_path = report_res["chart_path"]

        # Send plotly chart image if it exists on disk
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, "rb") as photo:
                await update.message.reply_photo(photo=photo)
                
        await update.message.reply_text(telegram_message)
        logger.info("[BOT] Weekly report sent to user_id: %s", user_id)
    except Exception as e:
        logger.error("[BOT] Error generating weekly report command: %s", str(e), exc_info=True)
        await update.message.reply_text(f"❌ Failed to generate weekly report: {e}")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays the command list and welcome message.
    """
    welcome_text = (
        "👋 Welcome to RestIQ — your personal sleep concierge!\n\n"
        "I'll check in with you every morning to track your sleep.\n"
        "Each week you'll get a visual report with insights.\n\n"
        "Commands:\n"
        "/checkin — log your sleep now\n"
        "/report — get your weekly sleep report\n"
        "/help — show this message\n\n"
        "Or just reply naturally to my morning check-in!"
    )
    await update.message.reply_text(welcome_text)


# ──────────────────────────────────────────────────────────────────────────────
# Background Tasks / Scheduled Messages
# ──────────────────────────────────────────────────────────────────────────────

async def send_daily_checkins(app: Application):
    """
    Loops through all users in the SQLite database and sends them their morning check-in prompt.
    """
    logger.info("[BOT] Starting scheduled daily check-ins...")
    try:
        conn = sqlite3.connect("sleep_data.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        rows = cursor.fetchall()
        conn.close()
        
        user_ids = [row[0] for row in rows]
        logger.info("[BOT] Found %d users in database for daily check-in.", len(user_ids))
        
        count = 0
        for user_id in user_ids:
            try:
                # Retrieve history and build customized daily prompt
                latest_entry = await asyncio.to_thread(run_get_latest, user_id)
                prompt = await asyncio.to_thread(run_daily_prompt, user_id, latest_entry)
                
                await app.bot.send_message(chat_id=int(user_id), text=prompt)
                count += 1
            except Exception as e_user:
                logger.error("[BOT] Failed to send daily check-in to user %s: %s", user_id, str(e_user))
                
        logger.info("[BOT] Daily check-ins sent to %d users", count)
    except Exception as e:
        logger.error("[BOT] Error executing send_daily_checkins: %s", str(e), exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# Main Function
# ──────────────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("[BOT] TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        sys.exit(1)
        
    logger.info("[BOT] Initializing RestIQ bot...")
    
    app = Application.builder().token(token).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("checkin", handle_checkin_command))
    app.add_handler(CommandHandler("report", handle_report_command))
    app.add_handler(CommandHandler("help", handle_help))
    
    # Message handler for conversation
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("[BOT] RestIQ bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
