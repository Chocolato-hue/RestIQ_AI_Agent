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
import streamlit as st
# pyrefly: ignore [missing-import]
import plotly.graph_objects as go
from dotenv import load_dotenv
load_dotenv()

from pipeline import run_checkin, run_weekly_report
from agents.tracker import run_get_history
from agents.scheduler import run_evaluate_plan
from tools import profile as profile_tool

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="RestIQ", page_icon="🌙", layout="centered")

BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "your_restiq_bot")


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

with st.sidebar:
    st.markdown("### 🌙 RestIQ")
    st.caption("Sleep concierge dashboard")

    # If we got a user_id from the deep-link or a previous session, pre-fill it.
    user_id = st.text_input(
        "User ID",
        value=query_user_id or st.session_state.get("user_id", ""),
        help="Auto-filled after registration, or paste your existing ID.",
        key="sidebar_user_id_input",
    )
    if user_id:
        st.session_state["user_id"] = user_id

# ─────────────────────────────────────────────────────────────────────────────
# Registration gate — shown when no user_id is present
# ─────────────────────────────────────────────────────────────────────────────

if not user_id:
    st.title("🌙 RestIQ")
    st.subheader("Better sleep, one morning at a time.")
    st.write(
        "RestIQ tracks your nightly habits, scores your sleep, and nudges your "
        "bedtime based on real patterns — not generic advice."
    )

    st.divider()
    st.subheader("Create your account")

    with st.form("registration_form"):
        display_name = st.text_input(
            "Your name",
            placeholder="Ada Lovelace",
            help="Used in reports and morning messages.",
        )
        wake_time = st.time_input(
            "Preferred wake-up time",
            value=__import__("datetime").time(7, 0),
            help="RestIQ will work backwards from this to recommend your bedtime.",
        )
        submitted = st.form_submit_button("Create account →", type="primary")

    if submitted:
        if not display_name.strip():
            st.warning("Enter your name to continue.")
        else:
            slug = _slugify(display_name)
            wake_str = wake_time.strftime("%H:%M")
            with st.spinner("Setting up your profile..."):
                try:
                    _call_register(slug, display_name.strip(), wake_str)
                    st.session_state["user_id"] = slug
                    st.session_state["just_registered"] = True
                    st.query_params["user_id"] = slug
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not create account: {e}")
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

# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

tab_checkin, tab_report, tab_plan = st.tabs(["Check-in", "Weekly Report", "Plan History"])

# ── Tab 1: Check-in ──────────────────────────────────────────────────────────

with tab_checkin:
    st.write("")
    st.markdown("### 💬 Conversational Daily Check-in")
    st.caption("Chat naturally with RestIQ. It asks adaptive follow-up questions, then gives structured coaching.")

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

    if "checkin_answers" not in st.session_state:
        st.session_state.checkin_answers = {}
    if "checkin_current_key" not in st.session_state:
        st.session_state.checkin_current_key = "sleep_feeling"

    def _chat_bubble(sender: str, message: str, is_user: bool = False):
        row_class = "user-row" if is_user else "bot-row"
        bubble_class = "user-bubble" if is_user else "bot-bubble"
        name = "You" if is_user else "RestIQ"

        st.markdown(
            f"""
            <div class="{row_class}">
                <div class="{bubble_class}">
                    <div class="bubble-name">{name}</div>
                    {message}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _next_question_key(answers: dict) -> str:
        if "sleep_feeling" not in answers:
            return "sleep_feeling"

        feeling = answers.get("sleep_feeling", "").lower()
        if any(word in feeling for word in ["bad", "terrible", "poor", "tired", "exhausted", "groggy", "not good"]):
            if "sleep_problem" not in answers:
                return "sleep_problem"

        if "bed_wake" not in answers:
            return "bed_wake"

        if "wakeups" not in answers:
            return "wakeups"

        wakeups = answers.get("wakeups", "").lower()
        if any(word in wakeups for word in ["yes", "twice", "three", "3", "2", "many", "multiple"]):
            if "wake_reason" not in answers:
                return "wake_reason"

        if "habits" not in answers:
            return "habits"

        habits = answers.get("habits", "").lower()
        if any(word in habits for word in ["coffee", "caffeine", "tea", "phone", "screen", "mobile", "scroll"]):
            if "habit_detail" not in answers:
                return "habit_detail"

        if "mood" not in answers:
            return "mood"

        return "done"

    question_text = {
        "sleep_feeling": "Good morning 😊 How did you sleep last night?",
        "sleep_problem": "Sorry to hear that. What do you think affected your sleep the most?",
        "bed_wake": "What time did you go to bed and wake up?",
        "wakeups": "Did you wake up during the night? If yes, how many times?",
        "wake_reason": "What do you think caused the wake-ups? Noise, stress, bathroom, discomfort, or something else?",
        "habits": "Did you have caffeine after 2 PM, exercise, or use screens before bed?",
        "habit_detail": "Can you give a little more detail about that habit? For example, when did you drink caffeine or how long did you use screens?",
        "mood": "How did you feel when you woke up?",
    }

    st.markdown("#### RestIQ Chat")
    st.markdown('<div class="chat-box">', unsafe_allow_html=True)

    for key, answer in st.session_state.checkin_answers.items():
        if key in question_text:
            _chat_bubble("RestIQ", question_text[key], is_user=False)
            _chat_bubble("You", answer, is_user=True)

    current_key = _next_question_key(st.session_state.checkin_answers)
    st.session_state.checkin_current_key = current_key

    if current_key != "done":
        _chat_bubble("RestIQ", question_text[current_key], is_user=False)
    else:
        _chat_bubble("RestIQ", "✅ I have enough information to analyze your sleep.", is_user=False)

    st.markdown("</div>", unsafe_allow_html=True)

    if current_key != "done":
        answer = st.text_input("Type your reply", key=f"answer_{current_key}")

        if st.button("Send", type="primary", use_container_width=True):
            if not answer.strip():
                st.warning("Please type a reply before sending.")
            else:
                st.session_state.checkin_answers[current_key] = answer.strip()
                st.rerun()

    else:
        combined_text = " ".join(
            f"{question_text.get(key, key)} Answer: {value}."
            for key, value in st.session_state.checkin_answers.items()
        )

        with st.expander("Review collected check-in"):
            review_labels = {
                "sleep_feeling": "Sleep feeling",
                "sleep_problem": "Main issue",
                "bed_wake": "Bed / Wake time",
                "wakeups": "Wake-ups",
                "wake_reason": "Wake-up reason",
                "habits": "Habits",
                "habit_detail": "Habit details",
                "mood": "Morning mood",
            }

            for key, label in review_labels.items():
                if key in st.session_state.checkin_answers:
                    st.markdown(f"**{label}:** {st.session_state.checkin_answers[key]}")

        if st.button("Analyze my sleep", type="primary", use_container_width=True):
            with st.spinner("Analyzing your sleep..."):
                try:
                    result = run_checkin(user_id, combined_text)
                    entry = result["entry"]
                    circadian = result["circadian"]
                    reply_text = result["reply_message"]

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

                    score = entry.score

                    if score >= 90:
                        score_label = "🟢 Excellent"
                    elif score >= 75:
                        score_label = "🟢 Great"
                    elif score >= 60:
                        score_label = "🟡 Good"
                    elif score >= 40:
                        score_label = "🟠 Fair"
                    else:
                        score_label = "🔴 Poor"

                    st.write("")
                    with st.container(border=True):
                        st.success("✅ Sleep logged successfully!")

                        col1, col2, col3 = st.columns(3)
                        col1.metric("⭐ Sleep Score", f"{score}/100", score_label)
                        col2.metric("🛌 Duration", f"{entry.sleep_duration}h")
                        col3.metric("⏰ Tonight's Bedtime", circadian.recommended_bedtime)

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
                            st.error(f"**🚨 Biggest Issue**\n\n{biggest_issue}")
                        with goal_col:
                            st.success(f"**🎯 Tonight's Goal**\n\n{tonight_goal}")

                        st.info(f"**💡 Why it matters**\n\n{why_it_matters}")

                        if result["plan_adjustment"].adjusted:
                            st.info(f"📋 **Plan update:** {result['plan_adjustment'].reason}")

                        with st.expander("🧠 How RestIQ analyzed your sleep"):
                            st.write(reply_text)

                except Exception:
                    st.error("Couldn't process your check-in right now.")
                    st.info("The AI service may be temporarily unavailable. Please try again later.")
                    st.caption("Technical details are available in the terminal logs.")

        if st.button("Start over", use_container_width=True):
            st.session_state.checkin_answers = {}
            st.session_state.checkin_current_key = "sleep_feeling"
            st.rerun()

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

            except Exception:
                st.error("Couldn't generate the weekly report right now.")
                st.info(
                    "This may happen if there are no sleep entries yet. "
                    "Add at least one check-in, and for best results use 7 daily entries."
                )
                st.caption("Technical details are available in the terminal logs.")

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