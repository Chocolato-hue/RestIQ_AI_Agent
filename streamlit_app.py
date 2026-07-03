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


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar — user identity
# ─────────────────────────────────────────────────────────────────────────────

query_user_id = st.query_params.get("user_id")
resolved_id = query_user_id or st.session_state.get("user_id")

if not resolved_id:
    import uuid
    resolved_id = f"guest-{uuid.uuid4().hex[:8]}"
    try:
        _call_register(resolved_id, "Guest", "07:00")
    except Exception as e:
        st.error(f"Could not start session: {e}")
        st.stop()
    st.session_state["just_registered"] = True

st.session_state["user_id"] = resolved_id
st.query_params["user_id"] = resolved_id
# Seed the widget's own state BEFORE the widget is created, so `value=` isn't ignored
st.session_state["sidebar_user_id_input"] = resolved_id

with st.sidebar:
    st.markdown("### 🌙 RestIQ")
    st.caption("Sleep concierge dashboard")

    user_id = st.text_input(
        "User ID",
        help="Auto-filled after registration, or paste your existing ID.",
        key="sidebar_user_id_input",
    )
    if user_id and user_id != resolved_id:
        st.session_state["user_id"] = user_id

# ─────────────────────────────────────────────────────────────────────────────
# Registration gate — shown when no user_id is present
# ─────────────────────────────────────────────────────────────────────────────

if not user_id:
    import uuid
    auto_id = f"guest-{uuid.uuid4().hex[:8]}"
    try:
        _call_register(auto_id, "Guest", "07:00")
        st.session_state["user_id"] = auto_id
        st.session_state["just_registered"] = True
        st.query_params["user_id"] = auto_id
        st.rerun()
    except Exception as e:
        st.error(f"Could not start session: {e}")
        st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Post-registration: show "Connect Telegram" banner (once)
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.pop("just_registered", False):
    telegram_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    st.success(f"✅ Account created! Your user ID is `{user_id}`.")
    st.info(
        "**Connect Telegram to get daily check-in reminders.**\n\n"
        f"Click the button below, then tap **Start** in Telegram."
    )
    st.caption("New to Telegram? Download the app or open web.telegram.org and log in first, then click below.")
    st.link_button("📲 Connect Telegram", telegram_link, type="primary")
    st.divider()

# ─────────────────────────────────────────────────────────────────────────────
# Main dashboard header
# ─────────────────────────────────────────────────────────────────────────────

st.title("🌙 RestIQ Dashboard")
st.caption(f"Showing data for user `{user_id}`")

# Persistent "Connect Telegram" button in the sidebar for already-registered users
with st.sidebar:
    st.divider()
    telegram_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    st.link_button("📲 Connect Telegram", telegram_link)
    st.caption("Links your account so you receive daily check-ins and weekly reports in Telegram.")

    # ── Age input (persistent, one-time) ─────────────────────────────────────
    st.divider()
    st.markdown("#### 🎂 Your Age")
    _stored_age = profile_tool.get_user_age(user_id)
    _age_input = st.number_input(
        "Age (years)",
        min_value=0.0,
        max_value=130.0,
        value=float(_stored_age) if _stored_age is not None else 25.0,
        step=1.0,
        help="Used to compare your sleep against CDC/AASM guidelines for your age group.",
        key="sidebar_age_input",
    )
    if st.button("Save age", key="save_age_btn", use_container_width=True):
        try:
            profile_tool.update_user_age(user_id, _age_input)
            st.success(f"✅ Age saved ({_age_input:.0f} yrs)")
        except ValueError as _e:
            st.error(f"⚠️ {_e}")
    if _stored_age is not None:
        st.caption(f"Saved: {_stored_age:.0f} years")

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

    if "checkin_session" not in st.session_state:
        session, _opener = concierge_agent.start_session(user_id, latest_entry)
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

            col1, col2, col3 = st.columns(3)
            col1.metric("⭐ Sleep Score", f"{score}/100", analysis["score_label"])
            col2.metric("🛌 Duration", f"{analysis['duration']}h")
            col3.metric("⏰ Tonight's Bedtime", analysis["bedtime"])

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

            if analysis.get("plan_adjusted"):
                st.info(f"📋 **Plan update:** {analysis['plan_reason']}")

    if not session_complete and not st.session_state.get("checkin_analyzed"):
        answer = st.text_input("Type your reply", key="concierge_reply")

        if st.button("Send", type="primary", use_container_width=True):
            if not answer.strip():
                st.warning("Please type a reply before sending.")
            else:
                with st.spinner("RestIQ is thinking..."):
                    try:
                        session, _reply = concierge_agent.process_turn(session, answer.strip())
                        st.session_state.checkin_session = concierge_agent.session_to_dict(session)
                        st.rerun()
                    except Exception as e:
                        err = str(e)
                        if "GOOGLE_API_KEY" in err:
                            st.error(err)
                        else:
                            st.error(f"Couldn't process your reply: {err}")
                            st.caption("Check your API key, model name (GEMINI_MODEL), and terminal logs.")

    elif session_complete and not st.session_state.get("checkin_analyzed"):
        with st.expander("Review collected check-in"):
            slots = session.slots.model_dump(exclude_none=True)
            if slots:
                for key, value in slots.items():
                    st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")
            else:
                st.write("Details captured in conversation above.")

        if st.button("Analyze my sleep", type="primary", use_container_width=True):
            with st.spinner("Analyzing your sleep..."):
                try:
                    transcript = concierge_agent.build_transcript(session)
                    result = run_checkin(user_id, transcript)
                    entry = result["entry"]
                    circadian = result["circadian"]
                    biggest_issue, tonight_goal, why_it_matters = _derive_coaching_focus(entry)
                    score = entry.score

                    st.session_state.checkin_analyzed = True
                    st.session_state.checkin_result = result["reply_message"]
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
                    }
                    st.rerun()

                except Exception:
                    st.error("Couldn't process your check-in right now.")
                    st.info("The AI service may be temporarily unavailable. Please try again later.")
                    st.caption("Technical details are available in the terminal logs.")

    elif st.session_state.get("checkin_analyzed") and st.session_state.get("checkin_analysis"):
        _render_checkin_analysis(st.session_state.checkin_analysis)

    if st.button("Start over", use_container_width=True):
        session, _opener = concierge_agent.start_session(user_id, latest_entry)
        st.session_state.checkin_session = concierge_agent.session_to_dict(session)
        st.session_state.checkin_analyzed = False
        st.session_state.checkin_result = None
        st.session_state.checkin_analysis = None
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
                        )

                        st.plotly_chart(fig, use_container_width=True)

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

    # ── Send to Telegram / Download ──────────────────────────────────────────
    st.write("")
    st.markdown("### 📤 Share Your Report")
    with st.container(border=True):
        _chat_id = profile_tool.get_telegram_chat_id(user_id)
        _chart_path = f"/tmp/restiq_report_{user_id}.png"
        _chart_exists = os.path.exists(_chart_path)

        if _chat_id:
            st.caption(f"📬 Linked to Telegram chat `{_chat_id}`")
            if st.button("📲 Send to Telegram", type="primary", use_container_width=True, key="send_telegram_report"):
                if not _chart_exists:
                    st.warning(
                        "No report chart found. Please click **Generate weekly report** first."
                    )
                elif not TELEGRAM_BOT_TOKEN:
                    st.error("TELEGRAM_BOT_TOKEN is not configured. Check your .env file.")
                else:
                    with st.spinner("Sending to Telegram..."):
                        try:
                            import requests as _req
                            _tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
                            # Send chart image
                            with open(_chart_path, "rb") as _f:
                                _resp = _req.post(
                                    f"{_tg_url}/sendPhoto",
                                    data={"chat_id": _chat_id, "caption": "📊 Your weekly RestIQ sleep report chart."},
                                    files={"photo": _f},
                                    timeout=15,
                                )
                            if not _resp.ok:
                                raise RuntimeError(f"Telegram API error: {_resp.text}")
                            st.success("✅ Chart sent to Telegram!")
                        except ValueError as _e:
                            st.warning(f"⚠️ {_e}")
                            st.info(
                                "Log at least 3 sleep entries via **/checkin** in Telegram "
                                "or the Check-in tab above, then try again."
                            )
                        except Exception as _e:
                            st.error(f"❌ Could not send to Telegram: {_e}")
                            st.caption("Check that your bot token and chat ID are correct.")
        else:
            telegram_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
            st.info(
                "**Telegram not connected.**\n\n"
                "Link your account to send reports directly to your Telegram chat."
            )
            st.link_button("📲 Connect Telegram", telegram_link, type="primary")
            st.caption(
                "After clicking, open Telegram and tap **Start**. "
                "New to Telegram? Log in at web.telegram.org first."
            )

        st.write("")
        if _chart_exists:
            with open(_chart_path, "rb") as _dl_f:
                st.download_button(
                    label="⬇️ Download Chart as PNG",
                    data=_dl_f,
                    file_name=f"restiq_weekly_report_{user_id}.png",
                    mime="image/png",
                    use_container_width=True,
                    key="download_report_png",
                )
        else:
            st.caption("Generate the weekly report above to enable download.")

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