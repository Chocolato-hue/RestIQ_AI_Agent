# RestIQ Improvement Prompt — Age Integration, UI Fixes & Telegram Clarification

## Context
I've added age-based sleep guidelines to RestIQ, but there are several issues. I need help fixing them and clarifying the Telegram integration.

---

## 1. Age Integration Issues

### Problem A: Agent Stops Asking Questions After Getting Age
**Current behavior:** After the user provides age, the conversation stops — the agent doesn't continue asking for sleep data.
**Expected behavior:** After age is captured, the agent should continue the check-in flow naturally (ask about bedtime, wake time, sleep quality, etc.).

**Fix:**
- In `tools/concierge.py`, ensure the `process_turn()` function checks if age is the *only* missing field. If age is captured but other slots are empty, the agent should move to the next question.
- The agent should not treat "age collection" as the end of the session.

### Problem B: Edge Cases — User Doesn't Answer Correctly
**Expected behavior:**
- If the user gives a non-numeric answer (e.g., "I'm in my thirties"), the agent should ask for clarification: *"Got it — but I need a specific number. Could you tell me your exact age in years?"*
- If the user gives an impossible age (e.g., 150), the agent should say: *"That age seems off — could you double-check?"*
- If the user skips the question entirely, the agent should ask once more, then proceed with a default (age = None).

**Fix:**
- Add validation logic in `tools/concierge.py` or the intake agent to handle these edge cases gracefully.
- If age is invalid or missing after 2 attempts, set `age_years = None` and continue the session.

---

## 2. UI Fixes — Input Box and Refresh Issues

### Problem C: Text Box Doesn't Refresh After Sending
**Current behavior:** After clicking "Send", the user's message stays in the input box.
**Expected behavior:** The input box should clear after sending.

**Fix:**
- In `streamlit_app.py`, ensure `st.session_state.concierge_reply = ""` is set **before** `st.rerun()`.
- Use `key="concierge_reply"` in the `st.text_input()` widget.
- Order: update session → clear input → `st.rerun()`.

### Problem D: What Is the "Start Over" Button For?
**Answer:** The "Start Over" button resets the current check-in session. It clears all collected data and starts a fresh conversation from scratch. This is useful if the user made a mistake or wants to start a new check-in.

**Fix (optional):** Rename it to "New Check-in" or "Start Fresh" for clarity.

---

## 3. Telegram Integration Clarification

### Current State:
- Telegram bot can be started with `uv run python bot.py`.
- It sends daily check-in prompts and weekly reports to linked users.
- Streamlit has a "Connect Telegram" button that generates a deep link: `t.me/<bot_username>?start=<user_id>`.

### Problem E: What is Telegram Used For?
**Simplified answer:** Telegram is for **daily follow-ups** (morning check-in prompts) and **weekly report delivery**. Streamlit is the **main dashboard** for reviewing data and generating reports.

**Clarification:**
- Users connect Telegram via Streamlit (click "Connect Telegram" → deep link).
- After linking, the bot sends:
  - Daily check-in prompts (scheduled via `AsyncIOScheduler`).
  - Weekly report (triggered by user or scheduled).
- Streamlit fetches data from the same SQLite database.

### Problem F: Should There Be an Option to Connect Telegram in the Check-in Flow?
**Yes** — after the user completes a check-in, you can offer:
*"Want to get daily reminders and weekly reports on Telegram? [Connect Telegram] button."*

**Fix (optional):** Add a "Connect Telegram" prompt after successful check-in analysis.

---

## 4. User Experience Improvements — Missed Check-ins

### Problem G: Missed Check-in Notification Placement
**Current state:** The "Missed check-in" notification appears somewhere in the flow.
**Question:** Should it be in the sidebar, or between the Check-in and Weekly Report tabs?

**Recommendation:** Move it to **the sidebar** — it's always visible, doesn't interrupt the flow, and is a gentle reminder rather than a disruptive pop-up.

**Implementation:**
```python
# In the sidebar, after the age input:
_missed_days = get_missed_checkin_days(user_id)
if _missed_days > 0:
    st.warning(f"⚠️ You haven't checked in for {_missed_days} day(s).")
    if st.button("Log now"):
        st.switch_page("streamlit_app.py?tab=checkin")  # or rerun with tab selection