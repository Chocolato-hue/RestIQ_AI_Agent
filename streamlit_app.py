"""
streamlit_app.py — RestIQ Web Dashboard

Primary entry point for new users (ADK Web is the backend brain; this is
the registration + linking UI). Flow:

  1. Landing page  → user enters display name + preferred wake time
  2. register_user MCP tool creates the profile, returns a stable user_id slug
  3. "Connect Telegram" button generates:   t.me/<BOT_USERNAME>?start=<user_id>
     Clicking that opens Telegram; bot.py's /start handler calls link_telegram.
  4. After registration the existing Check-in / Report / Plan tabs work as before.

No business logic lives here — every action calls into pipeline.py or directly
into the mcp_client.get() helper.
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
from mcp_client import get as mcp_get

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


def _call_register(user_id: str, username: str, wake_time: str) -> dict:
    return mcp_get("register_user", {
        "user_id": user_id,
        "username": username,
        "target_wake_time": wake_time,
    })


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
                    result = _call_register(slug, display_name.strip(), wake_str)
                    if result.get("success"):
                        st.session_state["user_id"] = slug
                        st.session_state["just_registered"] = True
                        st.query_params["user_id"] = slug
                        st.rerun()
                    else:
                        st.error(f"Registration failed: {result.get('error')}")
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
    st.markdown("### 📝 Daily Check-in")
    with st.container(border=True):
        raw_text = st.text_area(
            "Tell me about last night",
            placeholder=(
                "Went to bed at 11pm, woke up at 7am, woke up once, slept okay, "
                "felt a bit tired, no caffeine after 2, didn't exercise, used my phone before bed."
            ),
            height=120,
        )
        st.write("")
        if st.button("Submit check-in", type="primary", use_container_width=True):
            if not raw_text.strip():
                st.warning("Type something about last night's sleep first.")
            else:
                with st.spinner("Analyzing your sleep..."):
                    try:
                        result = run_checkin(user_id, raw_text)
                        st.write("")
                        with st.container(border=True):
                            st.success("✅ **Logged successfully!**")
                            entry = result["entry"]
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Sleep score", f"{entry.score}/100")
                            col2.metric("Duration", f"{entry.sleep_duration}h")
                            col3.metric("Tonight's bedtime", result["circadian"].recommended_bedtime)
                            st.divider()
                            if result["plan_adjustment"].adjusted:
                                st.info(f"📋 **Plan update:** {result['plan_adjustment'].reason}")
                            st.write(f"💬 {result['reply_message']}")
                    except Exception as e:
                        st.error(f"Couldn't process that check-in: {e}")

# ── Tab 2: Weekly Report ─────────────────────────────────────────────────────

with tab_report:
    st.write("")
    st.markdown("### 📈 Weekly Report")
    with st.container(border=True):
        st.write("Generate your comprehensive weekly sleep analysis.")
        st.write("")
        btn_generate = st.button("Generate weekly report", type="primary", use_container_width=True)
        
    if btn_generate:
        with st.spinner("Generating report..."):
            try:
                result = run_weekly_report(user_id)
                analysis = result["analysis"]
                report = result["report"]

                history = run_get_history(user_id, days=7)
                history_count = len(history) if history else 0

                main_issue = "Maintain consistency"
                if analysis.average_duration < 7:
                    main_issue = "Sleep duration below 7 hours"
                elif analysis.average_wake_ups > 1:
                    main_issue = "Frequent wake-ups"
                elif analysis.screen_time_impact and "drop" in analysis.screen_time_impact.lower():
                    main_issue = "Screen time before bed"
                elif analysis.caffeine_impact and "drop" in analysis.caffeine_impact.lower():
                    main_issue = "Late caffeine intake"

                verdict_val = analysis.verdict.value if hasattr(analysis.verdict, "value") else str(analysis.verdict)

                st.write("")
                st.divider()

                # --- SECTION: HEALTH SCORE ---
                st.markdown("## 🩺 Sleep Health Score")
                with st.container(border=True):
                    if verdict_val == "EXCELLENT":
                        st.success("### 🟢 Excellent")
                        st.write("Excellent week! Keep maintaining your routine.")
                    elif verdict_val == "ON_TRACK":
                        st.warning("### 🟡 On Track")
                        st.write("You're on track! Keep up the good work.")
                    elif verdict_val == "IMPROVING":
                        st.warning("### 🟠 Improving")
                        st.write("You're improving. Small bedtime adjustments will make a big difference.")
                    else:
                        st.error("### 🔴 Needs Attention")
                        st.write("Let's focus on consistency. Review the recommendations below.")

                st.write("")

                # --- SECTION: SUMMARY METRICS ---
                st.markdown("## 🎯 Weekly Summary")
                with st.container(border=True):
                    status_col, focus_col = st.columns(2)
                    with status_col:
                        if verdict_val == "EXCELLENT":
                            st.success("🟢 **Goal Status:** Achieved")
                        elif verdict_val == "ON_TRACK":
                            st.warning("🟡 **Goal Status:** On Track")
                        elif verdict_val == "IMPROVING":
                            st.warning("🟠 **Goal Status:** Improving")
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
                            st.metric("⏳ Avg Sleep", f"{analysis.average_duration}h")
                    with col3:
                        with st.container(border=True):
                            st.metric("🔔 Avg Wake-ups", f"{analysis.average_wake_ups}")
                    with col4:
                        with st.container(border=True):
                            st.metric("🔥 Streak", f"{analysis.streak_days} days")

                    st.write("") # Spacing

                    if analysis.best_night and analysis.worst_night:
                        if history_count < 2 or analysis.best_night.date == analysis.worst_night.date:
                            st.info("ℹ️ More daily check-ins are needed to compare your best and worst nights.")
                        else:
                            best_col, worst_col = st.columns(2)
                            best_col.success(
                                f"🌟 **Best night:** {analysis.best_night.date} "
                                f"({analysis.best_night.score}/100)"
                            )
                            worst_col.warning(
                                f"⚠️ **Needs attention:** {analysis.worst_night.date} "
                                f"({analysis.worst_night.score}/100)"
                            )

                if result["plan_adjustment"].triggered_by.value != "NONE":
                    st.write("")
                    st.info(f"📋 **Plan update:** {result['plan_adjustment'].reason}")

                st.write("")

                # --- SECTION: TRENDS ---
                st.markdown("## 📈 Sleep Trends")
                with st.container(border=True):
                    if history:
                        history_sorted = sorted(history, key=lambda e: e.date)
                        fig = go.Figure()
                        
                        x_days = [__import__('datetime').datetime.strptime(str(e.date), "%Y-%m-%d").strftime("%a") for e in history_sorted]
                        
                        fig.add_trace(go.Scatter(
                            x=x_days,
                            y=[e.score for e in history_sorted],
                            mode="lines+markers",
                            name="Sleep score",
                            line=dict(width=3, shape="spline"),
                            marker=dict(size=8),
                            hovertemplate="<b>%{x}</b>: %{y} Score<extra></extra>",
                        ))
                        fig.update_layout(
                            yaxis_range=[0, 100],
                            margin=dict(l=10, r=10, t=10, b=10),
                            height=300,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.caption("Not enough history yet to chart.")

                st.write("")

                # --- SECTION: INSIGHTS ---
                st.markdown("## 🧠 Insights & Patterns")
                with st.container(border=True):
                    if not analysis.patterns_detected:
                        st.info("No significant patterns detected this week.")
                    else:
                        for p in analysis.patterns_detected:
                            text_lower = p.lower()
                            if "exercise" in text_lower or "improved" in text_lower or "better" in text_lower:
                                st.success(f"✅ {p}")
                            elif "caffeine" in text_lower or "coffee" in text_lower:
                                st.warning(f"☕ {p}")
                            elif "screen time" in text_lower or "phone" in text_lower or "screen" in text_lower:
                                st.warning(f"⚠️ {p}")
                            elif "consistent" in text_lower or "schedule" in text_lower:
                                st.info(f"🌙 {p}")
                            elif "reduced" in text_lower or "affected" in text_lower or "poor" in text_lower or "late" in text_lower:
                                st.warning(f"⚠️ {p}")
                            else:
                                st.info(f"💡 {p}")

                st.write("")

                # --- SECTION: ACTION PLAN ---
                st.markdown("## 📋 Action Plan")
                st.write("")
                st.markdown("#### Priority Recommendations")
                for idx, r in enumerate(analysis.recommendations, start=1):
                    parts = r.split(":", 1)
                    if len(parts) > 1:
                        title = parts[0].strip()
                        explanation = parts[1].strip()
                    else:
                        # Fallback if there is no colon
                        sentence_parts = r.split(". ", 1)
                        if len(sentence_parts) > 1:
                            title = sentence_parts[0].strip() + "."
                            explanation = sentence_parts[1].strip()
                        else:
                            title = "Action Item"
                            explanation = r.strip()

                    with st.container(border=True):
                        st.markdown(f"**🎯 Priority {idx} | {title}**")
                        st.write(explanation)

                st.write("")
                st.markdown("#### Next Week Focus")
                st.success(report.next_week_goal)

                if report.milestone_message:
                    st.write("")
                    st.success(f"🏆 {report.milestone_message}")

            except Exception as e:
                st.error(f"Couldn't generate the report: {e}")

# ── Tab 3: Plan History ──────────────────────────────────────────────────────

with tab_plan:
    st.write("")
    st.markdown("### 🎯 Adaptive Plan")
    st.caption("Re-evaluates your plan the same way the weekly report does, without committing a change.")
    with st.container(border=True):
        if st.button("Check current plan status", use_container_width=True):
            with st.spinner("Evaluating..."):
                try:
                    adjustment = run_evaluate_plan(user_id, commit_weekly_adjustment=False)
                    st.divider()
                    st.markdown("#### Plan Status")
                    st.metric("Status", adjustment.status.value)
                    if adjustment.rolling_avg_score is not None:
                        col1, col2 = st.columns(2)
                        with col1:
                            with st.container(border=True):
                                st.metric("This week's avg", adjustment.rolling_avg_score)
                        with col2:
                            if adjustment.previous_week_avg_score is not None:
                                with st.container(border=True):
                                    st.metric("Last week's avg", adjustment.previous_week_avg_score)
                    
                    st.write("")
                    st.info(f"**Reasoning:** {adjustment.reason}")
                    if adjustment.new_target_bedtime:
                        st.success(f"**Current target bedtime:** {adjustment.new_target_bedtime}")
                except Exception as e:
                    st.error(f"Couldn't evaluate the plan: {e}")