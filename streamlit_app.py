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
    st.subheader("Log last night's sleep")
    raw_text = st.text_area(
        "Tell me about last night",
        placeholder=(
            "Went to bed at 11pm, woke up at 7am, woke up once, slept okay, "
            "felt a bit tired, no caffeine after 2, didn't exercise, used my phone before bed."
        ),
        height=120,
    )
    if st.button("Submit check-in", type="primary"):
        if not raw_text.strip():
            st.warning("Type something about last night's sleep first.")
        else:
            with st.spinner("Analyzing your sleep..."):
                try:
                    result = run_checkin(user_id, raw_text)
                    st.success("Logged!")
                    entry = result["entry"]
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Sleep score", f"{entry.score}/100")
                    col2.metric("Duration", f"{entry.sleep_duration}h")
                    col3.metric("Tonight's bedtime", result["circadian"].recommended_bedtime)
                    if result["plan_adjustment"].adjusted:
                        st.info(f"📋 Plan update: {result['plan_adjustment'].reason}")
                    st.text(result["reply_message"])
                except Exception as e:
                    st.error(f"Couldn't process that check-in: {e}")

# ── Tab 2: Weekly Report ─────────────────────────────────────────────────────

with tab_report:
    st.subheader("This week's report")
    if st.button("Generate weekly report"):
        with st.spinner("Generating report..."):
            try:
                result = run_weekly_report(user_id)
                analysis = result["analysis"]
                report = result["report"]

                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Avg score", f"{analysis.average_score}/100")
                col2.metric("Avg duration", f"{analysis.average_duration}h")
                col3.metric("Avg wake-ups", f"{analysis.average_wake_ups}")
                col4.metric("Streak", f"{analysis.streak_days} days")

                if result["plan_adjustment"].triggered_by.value != "NONE":
                    st.info(f"📋 Plan update: {result['plan_adjustment'].reason}")

                history = run_get_history(user_id, days=7)
                if history:
                    history_sorted = sorted(history, key=lambda e: e.date)
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[e.date for e in history_sorted],
                        y=[e.score for e in history_sorted],
                        mode="lines+markers",
                        name="Sleep score",
                        line=dict(width=3),
                    ))
                    fig.update_layout(
                        yaxis_range=[0, 100],
                        margin=dict(l=10, r=10, t=10, b=10),
                        height=300,
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("Not enough history yet to chart.")

                st.markdown("**Patterns detected**")
                for p in analysis.patterns_detected:
                    st.write(f"- {p}")

                st.markdown("**Recommendations**")
                for r in analysis.recommendations:
                    st.write(f"- {r}")

                st.markdown(f"**Next week's goal:** {report.next_week_goal}")
                if report.milestone_message:
                    st.success(report.milestone_message)

            except Exception as e:
                st.error(f"Couldn't generate the report: {e}")

# ── Tab 3: Plan History ──────────────────────────────────────────────────────

with tab_plan:
    st.subheader("Adaptive plan")
    st.caption("Re-evaluates your plan the same way the weekly report does, without committing a change.")
    if st.button("Check current plan status"):
        with st.spinner("Evaluating..."):
            try:
                adjustment = run_evaluate_plan(user_id, commit_weekly_adjustment=False)
                st.metric("Status", adjustment.status.value)
                if adjustment.rolling_avg_score is not None:
                    col1, col2 = st.columns(2)
                    col1.metric("This week's avg", adjustment.rolling_avg_score)
                    if adjustment.previous_week_avg_score is not None:
                        col2.metric("Last week's avg", adjustment.previous_week_avg_score)
                st.write(adjustment.reason)
                if adjustment.new_target_bedtime:
                    st.caption(f"Current target bedtime: **{adjustment.new_target_bedtime}**")
            except Exception as e:
                st.error(f"Couldn't evaluate the plan: {e}")