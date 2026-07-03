# RestIQ Weekly Report Enhancements – Change Summary

## Overview
We added a few safety checks and user‑friendly UI features to make the **weekly report** generation more reliable and convenient. Below is a plain‑English description of each change and why it matters.

---

### 1️⃣ `tools/reporting.py`
- **What we changed**: Added a guard that requires **at least 3 sleep entries** before a report can be generated. If there are fewer entries, a clear `ValueError` is raised with instructions.
- **Why it improves the app**: Prevents the AI from trying to draw a chart from insufficient data, which previously produced a generic error. Users now get a helpful prompt telling them exactly how to add more data.

---

### 2️⃣ `bot.py`
- **What we changed**: Split the exception handling in `handle_report_command()`.
  - `except ValueError` now sends a friendly Telegram message that explains the “need more sleep data” situation.
  - `except Exception` continues to handle unexpected failures.
- **Why it improves the app**: Telegram users see a clear, actionable message instead of a vague “something went wrong” notice.

---

### 3️⃣ `streamlit_app.py`
- **What we changed**:
  1. **Weekly report UI** now catches `ValueError` and shows a warning with step‑by‑step instructions on how to log more sleep.
  2. Added a **“Share Your Report”** section with three actions:
     - **Send to Telegram** – pushes the generated PNG chart directly to the linked Telegram chat.
     - **Connect Telegram** – shown when the user has not linked their account; a deep‑link button guides them through the linking flow.
     - **Download as PNG** – lets the user download the chart locally.
  3. Imported `get_telegram_chat_id` from `tools.profile` and read `TELEGRAM_BOT_TOKEN` from the environment.
- **Why it improves the app**:
  - Users can instantly share the chart with their Telegram bot without leaving the dashboard.
  - Clear fallback options (download or link Telegram) keep the workflow smooth even if the bot isn’t linked.
  - Errors are displayed in a friendly way, reducing confusion.

---

### 4️⃣ `tools/profile.py`
- **What we changed**: Added `get_telegram_chat_id(user_id)` which returns the stored Telegram chat ID or `None`.
- **Why it improves the app**: Gives a clean, reusable way for any part of the code (e.g., Streamlit) to check whether a user is linked, avoiding duplicate DB logic.

---

## User‑Facing Benefits
- **Clear guidance** when there isn’t enough data.
- **One‑click sharing** of the weekly chart to Telegram.
- **Downloadable PNG** for offline use or sharing elsewhere.
- **Smooth onboarding** for new users via the “Connect Telegram” link.

---

*All existing functionality remains unchanged; the new logic only adds helpful checks and UI actions.*
