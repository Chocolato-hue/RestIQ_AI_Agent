import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import asyncio
import datetime
import sqlite3
from dotenv import load_dotenv

load_dotenv()

from logger_config import get_bot_logger
logger = get_bot_logger()

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from pipeline import run_checkin, run_weekly_report, run_daily_prompt
from agents.tracker import run_get_latest

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

from services import profile as profile_service


def _call_link_telegram(user_id: str, telegram_chat_id: str):
    return profile_service.link_telegram(user_id, telegram_chat_id)


# ──────────────────────────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start handler.

    Two paths:
    1. Plain /start  — first-time welcome, no deep-link payload.
    2. /start <user_id> — deep-link from the Streamlit "Connect Telegram"
       button. The payload is the web-registered user_id slug. We call
       link_telegram to bind this Telegram chat to that account, then confirm.
    """
    telegram_chat_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name

    # context.args contains everything after /start (space-separated)
    deep_link_payload = context.args[0] if context.args else None

    if deep_link_payload:
        # ── Deep-link path: bind web account → Telegram chat ──────────────
        logger.info(
            "[BOT] Deep-link /start from chat_id=%s with payload user_id=%s",
            telegram_chat_id, deep_link_payload
        )
        try:
            link = await asyncio.to_thread(
                _call_link_telegram, deep_link_payload, telegram_chat_id
            )
            if link.already_linked:
                msg = (
                    f"✅ Your Telegram is already linked to account *{deep_link_payload}*.\n\n"
                    "You'll continue receiving daily check-ins and weekly reports here. 🌙"
                )
            else:
                msg = (
                    f"✅ *Telegram linked successfully!*\n\n"
                    f"Your RestIQ account `{deep_link_payload}` will now send daily check-ins "
                    f"and weekly reports to this chat.\n\n"
                    "Use /checkin to log your first sleep, or wait for my morning message!"
                )
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception as e:
            logger.error("[BOT] Exception in deep-link /start: %s", str(e), exc_info=True)
            await update.message.reply_text(
                f"❌ Something went wrong while linking your account: {e}"
            )
    else:
        # ── Plain /start path: welcome ─────────────────────────────────────
        logger.info("[BOT] Plain /start from user: %s", username)
        welcome_text = (
            "👋 Welcome to RestIQ — your personal sleep concierge!\n\n"
            "I'll check in with you every morning to track your sleep.\n"
            "Each week you'll get a visual report with insights.\n\n"
            "Commands:\n"
            "/checkin — log your sleep now\n"
            "/report — get your weekly sleep report\n"
            "/help — show this message\n\n"
            "Or just reply naturally to my morning check-in!\n\n"
            "💡 Tip: register on the web dashboard and use the "
            "'Connect Telegram' button to link your account."
        )
        await update.message.reply_text(welcome_text)


async def handle_checkin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    logger.info("[BOT] Awaiting check-in from user_id: %s", user_id)
    await update.message.reply_text("🌙 Tell me about last night's sleep...")
    context.user_data["awaiting_checkin"] = True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or update.effective_user.first_name
    message_text = update.message.text
    logger.info("[BOT] Message received from %s", username)

    if context.user_data.get("awaiting_checkin"):
        await update.message.reply_text("⏳ Analyzing your sleep...")
        try:
            checkin_res = await asyncio.to_thread(run_checkin, user_id, message_text)
            await update.message.reply_text(checkin_res["reply_message"])
            context.user_data["awaiting_checkin"] = False
            logger.info("[BOT] Check-in complete, score: %s", checkin_res["entry"].score)
        except Exception as e:
            logger.error("[BOT] Error during run_checkin: %s", str(e), exc_info=True)
            await update.message.reply_text(f"❌ Oops, I had trouble parsing that check-in: {e}")
    else:
        try:
            latest_entry = await asyncio.to_thread(run_get_latest, user_id)
            prompt = await asyncio.to_thread(run_daily_prompt, user_id, latest_entry)
            await update.message.reply_text(prompt)
            context.user_data["awaiting_checkin"] = True
        except Exception as e:
            logger.error("[BOT] Error generating daily prompt: %s", str(e), exc_info=True)
            await update.message.reply_text(f"❌ Error starting check-in sequence: {e}")


async def handle_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    await update.message.reply_text("📊 Generating your weekly report...")
    try:
        report_res = await asyncio.to_thread(run_weekly_report, user_id)
        chart_path = report_res["chart_path"]
        if chart_path and os.path.exists(chart_path):
            with open(chart_path, "rb") as photo:
                await update.message.reply_photo(photo=photo)
        await update.message.reply_text(report_res["telegram_message"])
        logger.info("[BOT] Weekly report sent to user_id: %s", user_id)
    except Exception as e:
        logger.error("[BOT] Error generating weekly report: %s", str(e), exc_info=True)
        await update.message.reply_text(f"❌ Failed to generate weekly report: {e}")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 Welcome to RestIQ — your personal sleep concierge!\n\n"
        "Commands:\n"
        "/checkin — log your sleep now\n"
        "/report — get your weekly sleep report\n"
        "/help — show this message\n\n"
        "Or just reply naturally to my morning check-in!"
    )
    await update.message.reply_text(welcome_text)


# ──────────────────────────────────────────────────────────────────────────────
# Scheduled: daily check-ins broadcast
# ──────────────────────────────────────────────────────────────────────────────

async def send_daily_checkins(app: Application):
    """
    Sends morning check-in prompts to every user that has a telegram_chat_id
    linked. Falls back to user_id as chat_id for users who checked in via
    Telegram directly (pre-web-registration legacy path).
    """
    logger.info("[BOT] Starting scheduled daily check-ins...")
    try:
        conn = sqlite3.connect("sleep_data.db")
        cursor = conn.cursor()
        # Prefer telegram_chat_id when set; fall back to user_id for direct-bot users
        cursor.execute(
            "SELECT user_id, telegram_chat_id FROM users WHERE telegram_chat_id IS NOT NULL"
        )
        rows = cursor.fetchall()
        conn.close()

        count = 0
        for user_id, chat_id in rows:
            try:
                latest_entry = await asyncio.to_thread(run_get_latest, user_id)
                prompt = await asyncio.to_thread(run_daily_prompt, user_id, latest_entry)
                await app.bot.send_message(chat_id=int(chat_id), text=prompt)
                count += 1
            except Exception as e_user:
                logger.error(
                    "[BOT] Failed to send daily check-in to user %s (chat %s): %s",
                    user_id, chat_id, str(e_user)
                )

        logger.info("[BOT] Daily check-ins sent to %d users", count)
    except Exception as e:
        logger.error("[BOT] Error executing send_daily_checkins: %s", str(e), exc_info=True)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("[BOT] TELEGRAM_BOT_TOKEN not set. Exiting.")
        sys.exit(1)

    logger.info("[BOT] Initializing RestIQ bot...")
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("checkin", handle_checkin_command))
    app.add_handler(CommandHandler("report", handle_report_command))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("[BOT] RestIQ bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()