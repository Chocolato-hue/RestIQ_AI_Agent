"""
streamlit_app.py — RestIQ Web Dashboard

Primary entry point for new users (ADK Web is the backend brain; this is
the registration + linking UI). Flow:

  1. Landing page  → user enters display name + preferred wake time
  2. register_user MCP tool creates the profile, returns a stable user_id slug
  3. "Connect Telegram" button generates:   t.me/<BOT_USERNAME>?start=<user_id>
     Clicking that opens Telegram; bot.py's /start handler calls link_telegram.
  4. After registration the existing Check-in / Report / Plan tabs work as before.

No business logic lives here — every action calls into pipeline.py or
tools/ directly.
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import re
import datetime
import streamlit as st
# pyrefly: ignore [missing-import]
import plotly.graph_objects as go
from dotenv import load_dotenv
load_dotenv(override=True)

GEMINI_CONFIGURED = bool(os.environ.get("GOOGLE_API_KEY", "").strip())

from pipeline import run_checkin, run_weekly_report, run_backfill_checkin
from agents.tracker import run_get_history, run_get_latest
from agents.scheduler import run_evaluate_plan
from agents import concierge as concierge_agent
from tools import profile as profile_tool
from tools.profile import (
    update_preferred_checkin_time,
    get_preferred_checkin_time,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="RestIQ", page_icon="🌙", layout="centered")

BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "your_restiq_bot")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Turns a display name into a URL-safe, lowercase, hyphenated user_id slug."""
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "user"


def _call_register(user_id: str, username: str, wake_time: str):
    return profile_tool.register_user(user_id, username, wake_time)


def _seed_demo_sleep_data(user_id: str) -> None:
    """Insert 5 realistic sleep entries if fewer than 3 exist (demo only)."""
    import sqlite3
    from db.sqlite import DB_FILE
    from tools.storage import store_sleep_data
    from tools.scoring import compute_sleep_score
    from schemas import SleepEntrySchema, SleepQuality, MoodOnWake

    conn = sqlite3.connect(DB_FILE)
    count = conn.execute(
        "SELECT COUNT(*) FROM sleep_entries WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    conn.close()
    if count >= 3:
        return

    today = datetime.date.today()
    seed_rows = [
        (5, "22:45", "06:30", 7.75, 0, SleepQuality.GOOD, MoodOnWake.GOOD, False, True, False, 4, 4, "Solid night after morning run."),
        (4, "23:45", "07:00", 7.25, 2, SleepQuality.FAIR, MoodOnWake.TIRED, True, False, True, 3, 3, "Late coffee and scrolling."),
        (3, "22:30", "06:45", 8.25, 0, SleepQuality.EXCELLENT, MoodOnWake.GREAT, False, True, False, 5, 5, "Best sleep this week."),
        (2, "23:15", "07:15", 8.0, 1, SleepQuality.GOOD, MoodOnWake.GOOD, False, False, True, 4, 4, "Watched TV before bed."),
        (1, "22:00", "06:30", 8.5, 0, SleepQuality.EXCELLENT, MoodOnWake.GREAT, False, True, False, 5, 5, "Early to bed, felt refreshed."),
    ]
    for days_ago, *fields in seed_rows:
        entry = SleepEntrySchema(
            user_id=user_id,
            date=today - datetime.timedelta(days=days_ago),
            bedtime=fields[0], wake_time=fields[1], sleep_duration=fields[2],
            wake_up_count=fields[3], sleep_quality=fields[4], mood_on_wake=fields[5],
            caffeine_after_2pm=fields[6], exercise_today=fields[7],
            screen_time_before_bed=fields[8], focus_level=fields[9],
            energy_level=fields[10], notes=fields[11],
        )
        entry.score = compute_sleep_score(entry)
        store_sleep_data(entry)

# ─────────────────────────────────────────────────────────────────────────────
# Telegram Helper
# ─────────────────────────────────────────────────────────────────────────────

def send_to_telegram(chat_id: str, message: str, photo_path: str = None):
    """Send message or photo to Telegram from Streamlit."""
    if not TELEGRAM_BOT_TOKEN:
        st.error("TELEGRAM_BOT_TOKEN is not set in .env")
        return False
    try:
        import requests
        base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/"
        
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as f:
                response = requests.post(
                    base_url + "sendPhoto",
                    data={"chat_id": chat_id, "caption": message},
                    files={"photo": f},
                    timeout=15
                )
        else:
            response = requests.post(
                base_url + "sendMessage",
                json={"chat_id": chat_id, "text": message},
                timeout=10
            )
        
        return response.ok
    except Exception as e:
        st.error(f"Failed to send to Telegram: {e}")
        return False
# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — user identity
# ─────────────────────────────────────────────────────────────────────────────

DEMO_USER_ID = "demo-user"

try:
    profile_tool.get_user_profile(DEMO_USER_ID)
except ValueError:
    _call_register(DEMO_USER_ID, "Demo User", "07:00")

user_id = DEMO_USER_ID
st.session_state["user_id"] = user_id
st.query_params["user_id"] = user_id
st.session_state["sidebar_user_id_input"] = user_id

_seed_demo_sleep_data(user_id)

with st.sidebar:
    st.markdown("### 🌙 RestIQ")
    st.caption("Sleep concierge dashboard")

    st.text_input(
        "User ID",
        value=user_id,
        disabled=True,
        key="sidebar_user_id_input",
    )

    # ── Follow-up Scheduler ──────────────────────────────────────────────────
    st.divider()
    st.markdown("#### ⏰ Daily Reminder")
    _saved_time = get_preferred_checkin_time(user_id)
    _default_time = datetime.time(8, 0)
    if _saved_time:
        try:
            _h, _m = map(int, _saved_time.split(":"))
            _default_time = datetime.time(_h, _m)
        except Exception:
            pass
    _reminder_time = st.time_input(
        "Remind me at",
        value=_default_time,
        key="reminder_time_input",
        help="Set the time you'd like RestIQ to send a daily check-in nudge.",
    )
    if st.button("💾 Save reminder", key="save_reminder_btn", use_container_width=True):
        try:
            _time_str = _reminder_time.strftime("%H:%M")
            update_preferred_checkin_time(user_id, _time_str)
            st.success(f"✅ Reminder set for {_time_str} daily")
        except Exception as _e:
            st.error(f"⚠️ {_e}")
    _chat_id_for_reminder = profile_tool.get_telegram_chat_id(user_id)
    if not _chat_id_for_reminder:
        st.caption("📲 Connect Telegram below to receive push reminders at this time.")
    else:
        if _saved_time:
            st.caption(f"📬 Reminders sent to Telegram at **{_saved_time}** daily.")

    # ── Missed check-in notification (Fix G: moved to sidebar) ───────────────
    st.divider()
    try:
        _history_recent = run_get_history(user_id, days=2)
        _today = datetime.date.today()
        _logged_dates = {e.date for e in (_history_recent or [])}
        _yesterday = _today - datetime.timedelta(days=1)
        if _yesterday not in _logged_dates and _today not in _logged_dates:
            st.warning("⚠️ You haven't logged last night's sleep yet.")
            if st.button("📝 Log now", key="sidebar_log_now", use_container_width=True):
                st.session_state["active_tab"] = "checkin"
                st.rerun()
    except Exception:
        pass  # Silently skip if history unavailable

# ─────────────────────────────────────────────────────────────────────────────
# Main dashboard header
# ─────────────────────────────────────────────────────────────────────────────

st.title("🌙 RestIQ Dashboard")
st.caption(f"Showing data for user `{user_id}`")


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_checkin, tab_report, tab_plan = st.tabs(["Check-in", "Weekly Report", "Plan History"])

# ── Tab 1: Check-in ──────────────────────────────────────────────────────────

with tab_checkin:
    st.write("")
    st.markdown("### 💬 Conversational Daily Check-in")
    st.caption("Tell RestIQ about last night in your own words — it'll only ask what's still missing.")

    if not GEMINI_CONFIGURED:
        st.error(
            "**Gemini API key missing.** The check-in chat needs `GOOGLE_API_KEY` in your `.env` file. "
            "Get a free key at [Google AI Studio](https://aistudio.google.com/apikey), then restart Streamlit."
        )

    st.markdown(
        """
        <style>
        .chat-box {
            background-color: transparent;
            border: none;
            padding: 6px 0;
            margin-bottom: 12px;
        }
        .bot-row {
            display: flex;
            justify-content: flex-start;
            margin: 8px 0;
        }
        .user-row {
            display: flex;
            justify-content: flex-end;
            margin: 8px 0;
        }
        .bot-bubble {
            background-color: #1f2c34;
            color: #ffffff;
            padding: 12px 14px;
            border-radius: 16px 16px 16px 4px;
            max-width: 72%;
            line-height: 1.45;
        }
        .user-bubble {
            background-color: #005c4b;
            color: #ffffff;
            padding: 12px 14px;
            border-radius: 16px 16px 4px 16px;
            max-width: 72%;
            line-height: 1.45;
        }
        .bubble-name {
            font-size: 0.75rem;
            font-weight: 700;
            opacity: 0.75;
            margin-bottom: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    latest_entry = run_get_latest(user_id)
    if "input_counter" not in st.session_state:
        st.session_state.input_counter = 0

    if "checkin_session" not in st.session_state:
        try:
            profile = profile_tool.get_user_profile(user_id)
            age = profile.age_years
        except:
            age = None
            
        session, _opener = concierge_agent.start_session(user_id, latest_entry, age_years=age)
        st.session_state.checkin_session = concierge_agent.session_to_dict(session)
        st.session_state.checkin_analyzed = False
        st.session_state.checkin_result = None
        st.session_state.checkin_analysis = None

    def _chat_bubble(sender: str, message: str, is_user: bool = False):
        row_class = "user-row" if is_user else "bot-row"
        bubble_class = "user-bubble" if is_user else "bot-bubble"
        name = "You" if is_user else "RestIQ"
        safe_message = message.replace("\n", "<br>")

        st.markdown(
            f"""
            <div class="{row_class}">
                <div class="{bubble_class}">
                    <div class="bubble-name">{name}</div>
                    {safe_message}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    session = concierge_agent.session_from_dict(st.session_state.checkin_session)

    st.markdown("#### RestIQ Chat")
    st.markdown('<div class="chat-box">', unsafe_allow_html=True)

    for msg in session.messages:
        _chat_bubble("You" if msg.role == "user" else "RestIQ", msg.content, is_user=(msg.role == "user"))

    if st.session_state.get("checkin_result"):
        _chat_bubble("RestIQ", st.session_state.checkin_result, is_user=False)

    st.markdown("</div>", unsafe_allow_html=True)

    session_complete = concierge_agent.is_complete(session)

    def _score_label(score: int) -> str:
        if score >= 90:
            return "🟢 Excellent"
        if score >= 75:
            return "🟢 Great"
        if score >= 60:
            return "🟡 Good"
        if score >= 40:
            return "🟠 Fair"
        return "🔴 Poor"

    def _derive_coaching_focus(entry) -> tuple[str, str, str]:
        biggest_issue = "Maintain consistency"
        tonight_goal = "Keep your bedtime and wake-up time consistent"
        why_it_matters = "A consistent routine helps your body predict when to sleep and wake."

        if entry.screen_time_before_bed:
            biggest_issue = "📱 Screen time before bed"
            tonight_goal = "Stop screens at least 60 minutes before bed"
            why_it_matters = "Screen light can delay melatonin release, making it harder to fall asleep."
        if entry.caffeine_after_2pm:
            biggest_issue = "☕ Late caffeine intake"
            tonight_goal = "Avoid caffeine after 2 PM"
            why_it_matters = "Caffeine can stay active for hours and reduce sleep quality."
        if entry.sleep_duration < 7:
            biggest_issue = "⏳ Short sleep duration"
            tonight_goal = "Go to bed 20–30 minutes earlier tonight"
            why_it_matters = "Sleeping less than 7 hours can increase tiredness and reduce focus the next day."
        if entry.wake_up_count > 1:
            biggest_issue = "🔔 Frequent wake-ups"
            tonight_goal = "Create a calmer wind-down routine before bed"
            why_it_matters = "Night interruptions reduce deep sleep and can make you feel tired in the morning."

        return biggest_issue, tonight_goal, why_it_matters

    def _render_checkin_analysis(analysis: dict):
        score = analysis["score"]
        st.write("")
        with st.container(border=True):
            st.success("✅ Sleep logged successfully!")

            # ── Prominent bedtime card ──────────────────────────────────
            st.markdown(
                f"""
                <div style="
                    background: linear-gradient(135deg, #1e3a5f 0%, #0f2b46 100%);
                    border-radius: 14px;
                    padding: 18px 24px;
                    margin: 10px 0 18px 0;
                    display: flex;
                    align-items: center;
                    gap: 16px;
                ">
                    <span style="font-size:2.4rem;">🌙</span>
                    <div>
                        <div style="color:#a0c4ff;font-size:0.78rem;font-weight:600;letter-spacing:0.05em;text-transform:uppercase;">Your ideal bedtime tonight</div>
                        <div style="color:#ffffff;font-size:2rem;font-weight:700;line-height:1.2;">{analysis['bedtime']}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            col1, col2 = st.columns(2)
            col1.metric("⭐ Sleep Score", f"{score}/100", analysis["score_label"])
            col2.metric("🛌 Duration", f"{analysis['duration']}h")

            st.divider()

            if score >= 90:
                st.success("🟢 **Excellent Night!**\n\nYou had an excellent night's sleep. Keep following this routine.")
            elif score >= 75:
                st.success("🟢 **Great Sleep!**\n\nYou're building healthy sleep habits. Keep up the consistency.")
            elif score >= 60:
                st.warning("🟡 **Good Progress**\n\nYour sleep is improving, but there are still a few habits worth refining.")
            elif score >= 40:
                st.warning("🟠 **Needs Improvement**\n\nToday's sleep quality wasn't ideal. Focus on tonight's recommendations.")
            else:
                st.error("🔴 **Poor Sleep Night**\n\nYour sleep was significantly affected. Let's improve it tonight.")

            st.write("")
            st.markdown("### 🧠 RestIQ's Analysis")

            issue_col, goal_col = st.columns(2)
            with issue_col:
                st.error(f"**🚨 Biggest Issue**\n\n{analysis['biggest_issue']}")
            with goal_col:
                st.success(f"**🎯 Tonight's Goal**\n\n{analysis['tonight_goal']}")

            st.info(f"**💡 Why it matters**\n\n{analysis['why_it_matters']}")

            # ── Coach narrative (Q1: bundled from LLM response) ─────────
            _narrative = analysis.get("coach_narrative", "")
            if _narrative:
                st.write("")
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, #1a2e1a 0%, #0d1f0d 100%);
                        border-left: 4px solid #4ade80;
                        border-radius: 0 10px 10px 0;
                        padding: 16px 20px;
                        margin: 8px 0;
                    ">
                        <div style="color:#86efac;font-size:0.78rem;font-weight:700;letter-spacing:0.05em;text-transform:uppercase;margin-bottom:8px;">🏋️ Your Coach Says</div>
                        <div style="color:#dcfce7;font-size:0.97rem;line-height:1.6;">{_narrative}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            if analysis.get("plan_adjusted"):
                st.info(f"📋 **Plan update:** {analysis['plan_reason']}")

    if not session_complete and not st.session_state.get("checkin_analyzed"):
            # Dynamic key to force reset
            input_key = f"concierge_reply_{st.session_state.get('input_counter', 0)}"
            
            answer = st.text_input(
                "Type your reply",
                key=input_key,
                placeholder="e.g. I slept from 11 PM to 7 AM, woke up once...",
            )

            if st.button("Send 💬", type="primary", use_container_width=True):
                if not answer or not answer.strip():
                    st.warning("Please type something before sending.")
                else:
                    with st.spinner("RestIQ is thinking..."):
                        try:
                            session, _reply = concierge_agent.process_turn(session, answer.strip())
                            st.session_state.checkin_session = concierge_agent.session_to_dict(session)
                            
                            # Increment counter to reset the input widget
                            st.session_state["input_counter"] = st.session_state.get("input_counter", 0) + 1
                            st.rerun()
                        except Exception as e:
                            err = str(e)
                            if "GOOGLE_API_KEY" in err:
                                st.error("Google API key is missing or invalid.")
                            else:
                                st.error(f"Couldn't process your reply: {err}")

    elif session_complete and not st.session_state.get("checkin_analyzed"):
            with st.expander("Review collected check-in"):
                slots = session.slots.model_dump(exclude_none=True)
                if slots:
                    for key, value in slots.items():
                        # Make it human readable
                        display_key = key.replace('_', ' ').title()
                        if key == "sleep_quality" and value:
                            display_key = "Sleep Quality"
                            value = value.value if hasattr(value, "value") else value
                        elif key == "mood_on_wake" and value:
                            display_key = "Mood on Wake"
                            value = value.value if hasattr(value, "value") else value
                        elif isinstance(value, bool):
                            value = "Yes" if value else "No"
                        
                        st.markdown(f"**{display_key}:** {value}")
                else:
                    st.write("No details captured yet.")

            if st.button("Analyze my sleep", type="primary", use_container_width=True):
                with st.spinner("Analyzing your sleep..."):
                    try:
                        transcript = concierge_agent.build_transcript(session)
                        result = run_checkin(user_id, transcript)
                        entry = result["entry"]
                        circadian = result["circadian"]
                        biggest_issue, tonight_goal, why_it_matters = _derive_coaching_focus(entry)
                        score = entry.score

                        # Pull coach narrative from session if the LLM already wrote one
                        _coach_text = session.coach_narrative or ""

                        st.session_state.checkin_analyzed = True
                        st.session_state.checkin_result = result["reply_message"]
                        # === UPDATE AGE IN PROFILE ===
                        if hasattr(session, 'age_years') and session.age_years and session.age_years > 0:
                            try:
                                profile_tool.update_user_age(user_id, session.age_years)
                                st.success(f"✅ Age updated to {session.age_years:.0f} years")
                            except Exception as age_err:
                                st.warning(f"Could not update age: {age_err}")
                        
                        st.session_state.checkin_analysis = {
                            "score": score,
                            "score_label": _score_label(score),
                            "duration": entry.sleep_duration,
                            "bedtime": circadian.recommended_bedtime,
                            "biggest_issue": biggest_issue,
                            "tonight_goal": tonight_goal,
                            "why_it_matters": why_it_matters,
                            "plan_adjusted": result["plan_adjustment"].adjusted,
                            "plan_reason": result["plan_adjustment"].reason,
                            "coach_narrative": _coach_text,
                        }
                        st.rerun()

                    except Exception:
                        st.error("Couldn't process your check-in right now.")
                        st.info("The AI service may be temporarily unavailable. Please try again later.")
                        st.caption("Technical details are available in the terminal logs.")

    elif st.session_state.get("checkin_analyzed") and st.session_state.get("checkin_analysis"):
        _render_checkin_analysis(st.session_state.checkin_analysis)

    if st.button("🔄 New Check-in", use_container_width=True):
        session, _opener = concierge_agent.start_session(user_id, latest_entry)
        st.session_state.checkin_session = concierge_agent.session_to_dict(session)
        st.session_state.checkin_analyzed = False
        st.session_state.checkin_result = None
        st.session_state.checkin_analysis = None
        st.session_state["input_counter"] = 0
        st.rerun()

    st.divider()
    st.markdown("### 🗓️ Add Missed Check-in")
    st.caption("Forgot to log a previous night? Add it here so your weekly report has complete data.")

    with st.container(border=True):
        missed_date = st.date_input(
            "Select missed sleep date",
            max_value=datetime.date.today(),
            key="missed_date",
        )

        c1, c2 = st.columns(2)

        with c1:
            bedtime = st.text_input("Bedtime", value="23:00", key="missed_bedtime")
            sleep_quality = st.selectbox(
                "Sleep quality",
                ["POOR", "FAIR", "GOOD", "EXCELLENT"],
                index=2,
                key="missed_sleep_quality",
            )
            wake_up_count = st.number_input(
                "Wake-ups",
                min_value=0,
                max_value=10,
                value=1,
                step=1,
                key="missed_wakeups",
            )
            focus_level = st.slider("Focus level", 1, 5, 3, key="missed_focus")

        with c2:
            wake_time = st.text_input("Wake time", value="07:00", key="missed_wake")
            mood_on_wake = st.selectbox(
                "Mood on wake",
                ["TERRIBLE", "TIRED", "OKAY", "GOOD", "GREAT"],
                index=3,
                key="missed_mood",
            )
            sleep_duration = st.number_input(
                "Sleep duration (hours)",
                min_value=0.0,
                max_value=14.0,
                value=8.0,
                step=0.5,
                key="missed_duration",
            )
            energy_level = st.slider("Energy level", 1, 5, 3, key="missed_energy")

        caffeine_after_2pm = st.checkbox("Caffeine after 2 PM", key="missed_caffeine")
        exercise_today = st.checkbox("Exercised that day", key="missed_exercise")
        screen_time_before_bed = st.checkbox("Screen time before bed", key="missed_screen")

        notes = st.text_area(
            "Notes",
            placeholder="Optional: phone use, stress, late dinner, noise, etc.",
            height=80,
            key="missed_notes",
        )

        if st.button("Save missed check-in", use_container_width=True):
            with st.spinner("Saving missed check-in..."):
                try:
                    result = run_backfill_checkin(
                        user_id=user_id,
                        selected_date=missed_date,
                        bedtime=bedtime,
                        wake_time=wake_time,
                        sleep_duration=sleep_duration,
                        wake_up_count=wake_up_count,
                        sleep_quality=sleep_quality,
                        mood_on_wake=mood_on_wake,
                        caffeine_after_2pm=caffeine_after_2pm,
                        exercise_today=exercise_today,
                        screen_time_before_bed=screen_time_before_bed,
                        focus_level=focus_level,
                        energy_level=energy_level,
                        notes=notes,
                    )

                    entry = result["entry"]

                    st.success("✅ Missed check-in added successfully!")
                    st.markdown(
                        f"""
📅 **Date:** {entry.date}

⭐ **Sleep Score:** {entry.score}/100

🛌 **Duration:** {entry.sleep_duration} hours
"""
                    )

                except Exception as e:
                    st.error(f"Could not save missed check-in: {e}")

# ── Tab 2: Weekly Report ─────────────────────────────────────────────────────

with tab_report:
    st.write("")
    st.markdown("### 📈 Weekly Report")
    st.caption("Review your last 7 days of sleep patterns, trends, and personalized recommendations.")

    with st.container(border=True):
        st.write("Generate your comprehensive weekly sleep analysis.")
        st.write("")
        btn_generate = st.button("Generate weekly report", type="primary", use_container_width=True)

    if btn_generate:
        with st.spinner("Generating your weekly sleep analysis..."):
            try:
                result = run_weekly_report(user_id)
                analysis = result["analysis"]
                report = result["report"]

                history = run_get_history(user_id, days=7)
                history_count = len(history) if history else 0

                verdict_val = analysis.verdict.value if hasattr(analysis.verdict, "value") else str(analysis.verdict)

                main_issue = "Maintain consistency"
                if analysis.average_duration < 7:
                    main_issue = "Sleep duration below 7 hours"
                elif analysis.average_wake_ups > 1:
                    main_issue = "Frequent wake-ups"
                elif analysis.screen_time_impact and "drop" in analysis.screen_time_impact.lower():
                    main_issue = "Screen time before bed"
                elif analysis.caffeine_impact and "drop" in analysis.caffeine_impact.lower():
                    main_issue = "Late caffeine intake"

                st.write("")
                st.divider()

                # ── Coach Summary (Q3: bundled in run_weekly_report) ─────
                _weekly_narrative = getattr(report, "coach_narrative", None)
                if _weekly_narrative:
                    st.markdown(
                        f"""
                        <div style="
                            background: linear-gradient(135deg, #1a2e1a 0%, #0d1f0d 100%);
                            border-left: 4px solid #4ade80;
                            border-radius: 0 12px 12px 0;
                            padding: 20px 24px;
                            margin-bottom: 20px;
                        ">
                            <div style="color:#86efac;font-size:0.78rem;font-weight:700;letter-spacing:0.06em;text-transform:uppercase;margin-bottom:10px;">🏋️ Coach Weekly Summary</div>
                            <div style="color:#dcfce7;font-size:1rem;line-height:1.7;">{_weekly_narrative}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # ---------------- HEALTH SCORE ----------------
                st.markdown("## 🩺 Sleep Health Score")
                with st.container(border=True):
                    if verdict_val == "EXCELLENT":
                        st.success("### 🟢 Excellent")
                        st.write("Your sleep routine looks strong this week. Keep maintaining the same habits.")
                    elif verdict_val == "ON_TRACK":
                        st.success("### 🟢 On Track")
                        st.write("You are moving in the right direction. Keep building consistency.")
                    elif verdict_val == "IMPROVING":
                        st.warning("### 🟡 Improving")
                        st.write("Your sleep is improving, but there are still a few habits to refine.")
                    else:
                        st.error("### 🔴 Needs Attention")
                        st.write("Your sleep needs focused improvement this week. Start with the action plan below.")

                st.write("")

                # ---------------- WEEKLY SUMMARY ----------------
                st.markdown("## 🎯 Weekly Summary")
                with st.container(border=True):
                    status_col, focus_col = st.columns(2)

                    with status_col:
                        if verdict_val == "EXCELLENT":
                            st.success("🟢 **Goal Status:** Achieved")
                        elif verdict_val == "ON_TRACK":
                            st.success("🟢 **Goal Status:** On Track")
                        elif verdict_val == "IMPROVING":
                            st.warning("🟡 **Goal Status:** Improving")
                        else:
                            st.error("🔴 **Goal Status:** Needs Improvement")

                    with focus_col:
                        st.info(f"🎯 **Main Focus:** {main_issue}")

                    st.divider()

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        with st.container(border=True):
                            st.metric("📈 Avg Score", f"{analysis.average_score}/100")
                    with col2:
                        with st.container(border=True):
                            st.metric("🛌 Avg Sleep", f"{analysis.average_duration}h")
                    with col3:
                        with st.container(border=True):
                            st.metric("🔔 Avg Wake-ups", f"{analysis.average_wake_ups}")
                    with col4:
                        with st.container(border=True):
                            st.metric("🔥 Streak", f"{analysis.streak_days} days")

                    # ── Age-Based Guideline Comparison ──
                    _stored_age = profile_tool.get_user_age(user_id)
                    if _stored_age is not None:
                        from tools.sleep_guideline import evaluate_duration_against_guideline
                        try:
                            _guideline = evaluate_duration_against_guideline(_stored_age, analysis.average_duration)
                            _verdict_str = _guideline["verdict"].value if hasattr(_guideline["verdict"], "value") else str(_guideline["verdict"])
                            _badge = "🟢 Within Range" if _guideline["within_range"] else ("🔴 Below Range" if _verdict_str == "NEEDS_ATTENTION" else "🟡 Above Range")
                            
                            st.markdown("#### 💤 Age-Based Guideline Comparison")
                            with st.container(border=True):
                                gcol1, gcol2 = st.columns([2, 1])
                                with gcol1:
                                    st.markdown(f"**Group:** {_guideline['age_band']}")
                                    st.markdown(f"**Recommended:** {_guideline['recommended_min_hours']}–{_guideline['recommended_max_hours']} hours/night")
                                with gcol2:
                                    st.markdown(f"**Status:**\n\n### {_badge}")
                                
                                st.info(_guideline["note"])
                                st.caption(f"Source: {_guideline['source']}")
                        except Exception as _e:
                            st.caption(f"Failed to load sleep guideline: {_e}")

                    st.write("")

                    if history_count < 7:
                        st.info(
                            f"ℹ️ You currently have {history_count} sleep day(s). "
                            "A full 7-day report will unlock stronger trends and comparisons."
                        )

                    if analysis.best_night and analysis.worst_night:
                        if history_count < 2 or analysis.best_night.date == analysis.worst_night.date:
                            st.info("More daily check-ins are needed to compare your best and worst nights.")
                        else:
                            best_col, worst_col = st.columns(2)
                            best_col.success(
                                f"🌟 **Best Night:** {analysis.best_night.date} "
                                f"({analysis.best_night.score}/100)"
                            )
                            worst_col.warning(
                                f"⚠️ **Needs Attention:** {analysis.worst_night.date} "
                                f"({analysis.worst_night.score}/100)"
                            )

                if result["plan_adjustment"].triggered_by.value != "NONE":
                    st.write("")
                    st.info(f"📋 **Plan Update:** {result['plan_adjustment'].reason}")

                st.write("")

                # ---------------- TRENDS ----------------
                st.markdown("## 📈 Sleep Trends")
                with st.container(border=True):
                    if history:
                        history_sorted = sorted(history, key=lambda e: e.date)
                        fig = go.Figure()

                        x_days = [
                            __import__("datetime").datetime.strptime(str(e.date), "%Y-%m-%d").strftime("%a")
                            for e in history_sorted
                        ]

                        fig.add_trace(go.Scatter(
                            x=x_days,
                            y=[e.score for e in history_sorted],
                            mode="lines+markers",
                            name="Sleep score",
                            line=dict(width=3, shape="spline"),
                            marker=dict(size=9),
                            hovertemplate="<b>%{x}</b>: %{y}/100<extra></extra>",
                        ))

                        fig.update_layout(
                            yaxis_range=[0, 100],
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=320,
                            xaxis_title="Day",
                            yaxis_title="Sleep Score",
                            paper_bgcolor="#1e293b",
                            plot_bgcolor="#1e293b",
                            font_color="#e2e8f0",
                        )

                        st.plotly_chart(fig, use_container_width=True)

                        _age = profile_tool.get_user_age(user_id)

                        def _grid_color(score):
                            s = score if score is not None else 0
                            if s <= 50:
                                return "#ef4444"
                            if s <= 70:
                                return "#eab308"
                            if s <= 85:
                                return "#86efac"
                            return "#4ade80"

                        def _fmt_clock(time_str):
                            h, m = map(int, time_str.split(":"))
                            if m == 0:
                                if h == 0:
                                    return "12am"
                                if h < 12:
                                    return f"{h}am"
                                if h == 12:
                                    return "12pm"
                                return f"{h - 12}pm"
                            if h == 0:
                                return f"12:{m:02d}am"
                            if h < 12:
                                return f"{h}:{m:02d}am"
                            if h == 12:
                                return f"12:{m:02d}pm"
                            return f"{h - 12}:{m:02d}pm"

                        def _fmt_clock_long(time_str):
                            h, m = map(int, time_str.split(":"))
                            if h == 0:
                                return f"12:{m:02d} AM"
                            if h < 12:
                                return f"{h}:{m:02d} AM"
                            if h == 12:
                                return f"12:{m:02d} PM"
                            return f"{h - 12}:{m:02d} PM"

                        def _fmt_short_date(entry_date):
                            if isinstance(entry_date, datetime.date):
                                d = entry_date
                            else:
                                d = datetime.datetime.strptime(str(entry_date), "%Y-%m-%d").date()
                            return f"{d.strftime('%b')} {d.day}"

                        def _bedtime_mark(bedtime):
                            h, _m = map(int, bedtime.split(":"))
                            if h < 6:
                                return "⚠️"
                            if h <= 23:
                                return "✅"
                            return "⚠️"

                        _coach_narrative = getattr(report, "coach_narrative", None)
                        _coach_section = ""
                        if _coach_narrative:
                            _coach_section = f"""
  <div class="section coach-box">
    <h3>Coach Summary</h3>
    <p>{_coach_narrative}</p>
  </div>"""

                        _grid_cells = ""
                        for _e in history_sorted:
                            _sc = _e.score if _e.score is not None else 0
                            _bt_label = _fmt_clock(_e.bedtime)
                            _date_label = _fmt_short_date(_e.date)
                            _grid_cells += (
                                f'<div style="display:inline-flex;flex-direction:column;align-items:center;margin:4px;">'
                                f'<span style="font-size:10px;color:#94a3b8;margin-bottom:4px;">{_bt_label}</span>'
                                f'<span title="Score: {_sc}/100" style="display:inline-block;width:28px;height:28px;'
                                f'background:{_grid_color(_sc)};border-radius:4px;cursor:default;"></span>'
                                f'<span style="font-size:10px;color:#94a3b8;margin-top:4px;">{_date_label}</span>'
                                f'</div>'
                            )

                        _goal_rows = ""
                        for _e in history_sorted:
                            _mark = _bedtime_mark(_e.bedtime)
                            _goal_rows += (
                                f'<li>{_fmt_short_date(_e.date)} — {_fmt_clock_long(_e.bedtime)} {_mark}</li>'
                            )

                        _patterns_html = "".join(
                            f"<li>{p}</li>" for p in (analysis.patterns_detected or [])
                        )
                        _recs_html = "".join(
                            f"<li>{r}</li>" for r in (analysis.recommendations or [])
                        )

                        _table_rows = ""
                        for _e in history_sorted:
                            _sc = _e.score if _e.score is not None else 0
                            _bar_color = _grid_color(_sc)
                            _table_rows += (
                                f"<tr>"
                                f"<td>{_e.date}</td>"
                                f"<td>{_fmt_clock_long(_e.bedtime)}</td>"
                                f"<td>{_fmt_clock_long(_e.wake_time)}</td>"
                                f"<td>{_e.sleep_duration}h</td>"
                                f'<td class="score-col">'
                                f'<span class="score-num">{_sc}</span>'
                                f'<div class="bar-bg"><div class="bar-fill" style="width:{_sc}%;background:{_bar_color};"></div></div>'
                                f"</td>"
                                f"</tr>"
                            )

                        _age_section = ""
                        if _age is not None:
                            if _age >= 65:
                                _min_h, _max_h, _band = 7, 8, "65+"
                            elif _age >= 26:
                                _min_h, _max_h, _band = 7, 9, "26–64"
                            else:
                                _min_h, _max_h, _band = 7, 9, "18–25"
                            _within = _min_h <= analysis.average_duration <= _max_h
                            _range_status = (
                                "Within recommended range"
                                if _within
                                else "Outside recommended range"
                            )
                            _age_section = f"""
  <div class="section">
    <h3>Age &amp; Guideline</h3>
    <p>Age: <strong>{_age:.0f}</strong> ({_band})</p>
    <p>CDC recommended: <strong>{_min_h}–{_max_h}h</strong>/night</p>
    <p>Your average: <strong>{analysis.average_duration}h</strong> — {_range_status}</p>
  </div>"""

                        _bedtime_rec = next(
                            (
                                r for r in analysis.recommendations
                                if "ideal" in r.lower() or "bedtime" in r.lower()
                            ),
                            None,
                        )
                        _bedtime_section = ""
                        if _bedtime_rec:
                            _bed_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _bedtime_rec)
                            _bedtime_section = f"""
  <div class="section highlight">
    <h3>Recommended Bedtime</h3>
    <p>{_bed_html}</p>
  </div>"""

                        _chart_html = fig.to_html(full_html=False, include_plotlyjs="cdn")
                        _report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>RestIQ Weekly Report — {user_id}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; background: #0f172a; color: #e2e8f0; }}
    h2, h3 {{ color: #4ade80; }}
    .section {{ margin: 1.5rem 0; padding: 1rem; background: #1e293b; border-radius: 8px; }}
    .section.highlight {{ background: #14532d; border-left: 4px solid #4ade80; }}
    .section.coach-box {{ background: linear-gradient(135deg, #1a2e1a 0%, #0d1f0d 100%); border-left: 4px solid #4ade80; }}
    .metrics-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 1.5rem 0; }}
    .metric-card {{ background: #1e293b; border-radius: 8px; padding: 16px; text-align: center; }}
    .metric-label {{ font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 8px; }}
    .metric-value {{ font-size: 28px; font-weight: 700; color: #4ade80; }}
    .grid-row {{ display: flex; flex-wrap: wrap; gap: 2px; margin-bottom: 12px; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 12px; color: #94a3b8; }}
    .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
    .legend i {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; }}
    .goal-list {{ margin: 8px 0 0 0; padding-left: 1.25rem; line-height: 1.8; }}
    .insights-list {{ margin: 8px 0 0 0; padding-left: 1.25rem; line-height: 1.7; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    th, td {{ padding: 10px 8px; text-align: left; border-bottom: 1px solid #334155; }}
    th {{ color: #4ade80; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
    .score-col {{ min-width: 120px; }}
    .score-num {{ display: inline-block; width: 28px; font-weight: 600; }}
    .bar-bg {{ display: inline-block; width: 80px; height: 8px; background: #334155; border-radius: 4px; vertical-align: middle; }}
    .bar-fill {{ height: 100%; border-radius: 4px; }}
  </style>
</head>
<body>{_coach_section}
  <h2>RestIQ Weekly Report</h2>
  <p>Verdict: <strong>{verdict_val}</strong></p>
  <div class="metrics-row">
    <div class="metric-card">
      <div class="metric-label">Avg Score</div>
      <div class="metric-value">{analysis.average_score}</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg Duration</div>
      <div class="metric-value">{analysis.average_duration}h</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Avg Wake-ups</div>
      <div class="metric-value">{analysis.average_wake_ups}</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Streak</div>
      <div class="metric-value">{analysis.streak_days}</div>
    </div>
  </div>
  <div class="section">
    <h3>Sleep Activity</h3>
    <div class="grid-row">{_grid_cells}</div>
    <div class="legend">
      <span><i style="background:#ef4444;"></i>Poor</span>
      <span><i style="background:#eab308;"></i>Fair</span>
      <span><i style="background:#86efac;"></i>Good</span>
      <span><i style="background:#4ade80;"></i>Excellent</span>
    </div>
  </div>
  <div class="section highlight">
    <h3>Bedtime Goal</h3>
    <p><strong>🎯 Goal: 10–11 PM</strong></p>
    <ul class="goal-list">{_goal_rows}</ul>
  </div>{_age_section}{_bedtime_section}
  <div class="section">
    <h3>Sleep Trends</h3>
    {_chart_html}
  </div>
  <div class="section">
    <h3>AI Insights</h3>
    <h4 style="color:#86efac;font-size:14px;margin:12px 0 6px;">Patterns Detected</h4>
    <ul class="insights-list">{_patterns_html}</ul>
    <h4 style="color:#86efac;font-size:14px;margin:16px 0 6px;">Recommendations</h4>
    <ol class="insights-list">{_recs_html}</ol>
  </div>
  <div class="section">
    <h3>Weekly Sleep Log</h3>
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Bedtime</th>
          <th>Wake Time</th>
          <th>Duration</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody>{_table_rows}</tbody>
    </table>
  </div>
</body>
</html>"""
                        with open(f"/tmp/restiq_report_{user_id}.html", "w", encoding="utf-8") as _hf:
                            _hf.write(_report_html)

                        if history_count < 3:
                            st.caption("Trend accuracy improves after at least 3 daily sleep entries.")
                    else:
                        st.caption("Not enough history yet to chart.")

                st.write("")

                # ---------------- WEEKLY INSIGHTS ----------------
                st.markdown("## 🧠 Weekly Insights")
                with st.container(border=True):
                    st.caption("RestIQ detected the most important patterns from this week's sleep data.")

                    insight_count = 0

                    if analysis.average_duration < 7:
                        st.warning(
                            f"⚠️ Your average sleep duration is {analysis.average_duration}h, "
                            "which is below the healthy 7–9 hour range."
                        )
                        insight_count += 1
                    elif 7 <= analysis.average_duration <= 9:
                        st.success(
                            f"✅ Your average sleep duration is {analysis.average_duration}h, "
                            "which is within the healthy 7–9 hour range."
                        )
                        insight_count += 1

                    if analysis.average_wake_ups > 1:
                        st.warning(
                            f"🔔 You woke up about {analysis.average_wake_ups} times per night on average. "
                            "Reducing interruptions can improve deep sleep quality."
                        )
                        insight_count += 1
                    else:
                        st.success("✅ Wake-ups are under control this week.")
                        insight_count += 1

                    if analysis.caffeine_impact:
                        if "drop" in analysis.caffeine_impact.lower():
                            st.warning(f"☕ Late caffeine appears to be affecting your sleep: {analysis.caffeine_impact}")
                        else:
                            st.info(f"☕ Caffeine pattern: {analysis.caffeine_impact}")
                        insight_count += 1

                    if analysis.screen_time_impact:
                        if "drop" in analysis.screen_time_impact.lower():
                            st.warning(f"📱 Screen time may be reducing your sleep quality: {analysis.screen_time_impact}")
                        else:
                            st.info(f"📱 Screen time pattern: {analysis.screen_time_impact}")
                        insight_count += 1

                    for p in analysis.patterns_detected:
                        text_lower = p.lower()
                        if "exercise" in text_lower or "improved" in text_lower or "better" in text_lower:
                            st.success(f"✅ {p}")
                        elif "caffeine" in text_lower or "coffee" in text_lower:
                            st.warning(f"☕ {p}")
                        elif "screen" in text_lower or "phone" in text_lower:
                            st.warning(f"📱 {p}")
                        elif "consistent" in text_lower or "schedule" in text_lower:
                            st.info(f"🌙 {p}")
                        elif "late" in text_lower or "poor" in text_lower or "reduced" in text_lower:
                            st.warning(f"⚠️ {p}")
                        else:
                            st.info(f"💡 {p}")
                        insight_count += 1

                    if insight_count == 0:
                        st.info("Not enough patterns detected yet. Keep logging daily to unlock better insights.")

                st.write("")

                # ---------------- ACTION PLAN ----------------
                st.markdown("## 📋 Personalized Action Plan")
                with st.container(border=True):
                    st.caption("Focus on the highest-impact changes for the next 7 days.")

                    priority_items = []

                    if analysis.average_duration < 7:
                        priority_items.append((
                            "Increase sleep duration",
                            "Go to bed 20–30 minutes earlier until your average sleep reaches at least 7 hours."
                        ))

                    if analysis.average_wake_ups > 1:
                        priority_items.append((
                            "Reduce night interruptions",
                            "Use a calmer wind-down routine, avoid late fluids, and keep the room cool before sleep."
                        ))

                    if analysis.caffeine_impact and "drop" in analysis.caffeine_impact.lower():
                        priority_items.append((
                            "Avoid late caffeine",
                            "Stop caffeine after 2 PM for the next 7 days and compare your score next week."
                        ))

                    if analysis.screen_time_impact and "drop" in analysis.screen_time_impact.lower():
                        priority_items.append((
                            "Reduce screen time before bed",
                            "Keep your phone away for 30–60 minutes before bedtime to improve sleep readiness."
                        ))

                    if analysis.average_duration >= 7 and analysis.average_wake_ups <= 1:
                        priority_items.append((
                            "Maintain consistency",
                            "Keep your bedtime and wake-up time within a 30-minute window this week."
                        ))

                    for r in analysis.recommendations:
                        if len(priority_items) >= 3:
                            break
                        priority_items.append(("Recommendation", r))

                    if not priority_items:
                        priority_items.append((
                            "Build a stable sleep routine",
                            "Keep a consistent sleep schedule and continue logging daily."
                        ))

                    for idx, (title, explanation) in enumerate(priority_items[:3], start=1):
                        with st.container(border=True):
                            st.markdown(f"**🎯 Priority {idx}: {title}**")
                            st.write(explanation)

                st.write("")

                # ---------------- NEXT WEEK FOCUS ----------------
                st.markdown("## 🎯 Next Week Focus")
                st.success(report.next_week_goal)

                if report.milestone_message:
                    st.write("")
                    st.success(f"🏆 {report.milestone_message}")

            except ValueError as _ve:
                st.warning(f"⚠️ {_ve}")
                st.info(
                    "**How to log more sleep:**\n"
                    "- Use the **Check-in tab** above and click *Analyze my sleep*, or\n"
                    "- Send `/checkin` to your RestIQ Telegram bot."
                )
            except Exception:
                st.error("Couldn't generate the weekly report right now.")
                st.info(
                    "The AI service may be temporarily unavailable. "
                    "Add at least 3 check-ins and try again."
                )
                st.caption("Technical details are available in the terminal logs.")

    # ── Share & Download ──────────────────────────────────────────
    st.write("")
    st.markdown("### 📤 Share Your Report")
    with st.container(border=True):
        _chart_path = f"/tmp/restiq_report_{user_id}.html"
        _chart_exists = os.path.exists(_chart_path)

        if _chart_exists:
            with open(_chart_path, "rb") as _dl_f:
                st.download_button(
                    label="⬇️ Download Chart as HTML",
                    data=_dl_f.read(),
                    file_name=f"restiq_weekly_report_{user_id}.html",
                    mime="text/html",
                    use_container_width=True,
                )
        else:
            st.download_button(
                label="Generate report first",
                data=b"",
                file_name=f"restiq_weekly_report_{user_id}.html",
                mime="text/html",
                use_container_width=True,
                disabled=True,
            )

# ── Tab 3: Plan History ──────────────────────────────────────────────────────

with tab_plan:
    st.write("")
    st.markdown("### 🎯 Adaptive Plan")
    st.caption("Understand whether your current sleep plan is working or needs adjustment.")

    with st.container(border=True):
        if st.button("Check current plan status", use_container_width=True):
            with st.spinner("Evaluating your sleep plan..."):
                try:
                    adjustment = run_evaluate_plan(user_id, commit_weekly_adjustment=False)

                    status_map = {
                        "IMPROVING": ("🟢 Improving", "Your sleep trend is moving in the right direction."),
                        "STABLE": ("🔵 Stable", "Your sleep pattern is consistent. Keep maintaining your routine."),
                        "DECLINING": ("🔴 Declining", "Your recent sleep trend needs attention."),
                        "INSUFFICIENT_DATA": ("🟡 Not enough data yet", "Log more nights so RestIQ can detect reliable trends."),
                    }

                    status_label, status_message = status_map.get(
                        adjustment.status.value,
                        ("ℹ️ Unknown", "RestIQ could not classify your current plan status yet.")
                    )

                    st.divider()
                    st.markdown("#### 🧭 Plan Status")

                    st.info(f"**Status:** {status_label}")
                    st.write(status_message)

                    col1, col2 = st.columns(2)

                    with col1:
                        with st.container(border=True):
                            if adjustment.rolling_avg_score is not None:
                                st.metric("This week's average", adjustment.rolling_avg_score)
                            else:
                                st.metric("This week's average", "Not enough data")

                    with col2:
                        with st.container(border=True):
                            if adjustment.previous_week_avg_score is not None:
                                st.metric("Last week's average", adjustment.previous_week_avg_score)
                            else:
                                st.metric("Last week's average", "Not enough data")

                    st.markdown("#### 🧠 Why this status?")
                    st.info(adjustment.reason)

                    st.markdown("#### 🎯 Current Plan")
                    if adjustment.new_target_bedtime:
                        st.success(f"Target bedtime: **{adjustment.new_target_bedtime}**")
                    else:
                        st.success("Target bedtime: **23:00**")

                    st.markdown("#### ✅ What should you do next?")
                    if adjustment.status.value == "INSUFFICIENT_DATA":
                        st.write("• Keep logging your sleep daily for at least 3–7 days.")
                        st.write("• RestIQ will start detecting patterns once enough history is available.")
                    elif adjustment.status.value == "IMPROVING":
                        st.write("• Continue following your current bedtime routine.")
                        st.write("• Avoid changing too many habits at once.")
                    elif adjustment.status.value == "DECLINING":
                        st.write("• Focus on your next-week goal from the Weekly Report.")
                        st.write("• Reduce late caffeine and screen time before bed.")
                    else:
                        st.write("• Maintain consistency in bedtime and wake-up time.")
                        st.write("• Review your Weekly Report for detailed recommendations.")

                except Exception as e:
                    st.error(f"Couldn't evaluate the plan: {e}")