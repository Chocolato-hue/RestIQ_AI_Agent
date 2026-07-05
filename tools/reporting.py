"""Weekly report generation with Plotly chart."""

import datetime
import logging
import os
import sqlite3

from schemas import WeeklyReportSchema

from tools.analysis import build_sleep_analysis
from db.sqlite import DB_FILE
from db.entries import ensure_entry_scores, row_to_entry
from tools.scoring import compute_sleep_score
from tools.profile import get_user_age

logger = logging.getLogger("tools.reporting")


def _generate_weekly_coach_narrative(analysis, entries: list, age_years=None) -> str:
    """Optional coach narrative using Gemini."""
    try:
        from google import genai
        from google.genai import types

        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not api_key:
            return ""

        client = genai.Client(api_key=api_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

        age_line = f"User age: {age_years:.0f} years." if age_years else "User age unknown."
        verdict = analysis.verdict.value if hasattr(analysis.verdict, "value") else str(analysis.verdict)

        prompt = (
            f"{age_line}\n"
            f"Weekly sleep stats:\n"
            f"  Average score: {analysis.average_score}/100\n"
            f"  Average duration: {analysis.average_duration}h\n"
            f"  Average wake-ups: {analysis.average_wake_ups}\n"
            f"  Streak: {analysis.streak_days} days\n"
            f"  Verdict: {verdict}\n"
            f"  Patterns: {'; '.join(analysis.patterns_detected[:3]) or 'none'}\n\n"
            "Write a warm, encouraging 2-3 sentence summary. Be specific about their average sleep and top pattern. "
            "End with one concrete action for next week. Return plain text only."
        )

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are RestIQ, a warm and encouraging sleep coach.",
                temperature=0.4,
            ),
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning("[REPORTING] Coach narrative failed: %s", e)
        return ""


def generate_report(user_id: str) -> WeeklyReportSchema:
    logger.info("[REPORTING] generate_report user_id=%s", user_id)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM sleep_entries WHERE user_id = ? ORDER BY date DESC",
        (user_id,),
    )
    rows = cursor.fetchall()

    cursor.execute(
        "SELECT total_entries, check_in_streak FROM users WHERE user_id = ?",
        (user_id,),
    )
    user_row = cursor.fetchone()
    total_entries = user_row[0] if user_row else 0
    check_in_streak = user_row[1] if user_row else 0
    conn.close()

    if not rows:
        raise ValueError("No sleep entries found. Please log your first night.")

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    entries = []
    for r in rows_sorted:
        entry = row_to_entry(r)
        if entry.score is None:
            entry.score = compute_sleep_score(entry)
        entries.append(entry)
    ensure_entry_scores(entries)

    days_logged = len(entries)

    # Dynamic title
    if days_logged >= 7:
        report_title = "Weekly Report"
    else:
        report_title = f"Partial Report ({days_logged} days logged)"

    # Build analysis
    age_years = get_user_age(user_id)
    analysis = build_sleep_analysis(user_id, days_logged, entries, check_in_streak, age_years=age_years)

    # Chart
    chart_path = f"/tmp/restiq_report_{user_id}.png"
    chart_exists = False
    if days_logged >= 2:
        try:
            import plotly.graph_objects as go
            import plotly.io as pio

            day_labels = []
            for d in [r["date"] for r in rows_sorted]:
                try:
                    day_labels.append(datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%a"))
                except:
                    day_labels.append(str(d))

            scores = [e.score for e in entries]
            colors = ["#10B981" if s >= 70 else "#F59E0B" if s >= 50 else "#EF4444" for s in scores]

            fig = go.Figure(data=[go.Bar(
                x=day_labels,
                y=scores,
                marker_color=colors,
                text=[f"{s}/100" for s in scores],
                textposition="outside",
            )])

            fig.update_layout(
                title={"text": report_title, "x": 0.5},
                xaxis_title="Day",
                yaxis_title="Sleep Score",
                yaxis=dict(range=[0, 105]),
                height=420,
            )

            os.makedirs(os.path.dirname(chart_path), exist_ok=True)
            pio.write_image(fig, chart_path, engine="kaleido")
            chart_exists = True
        except Exception as e:
            logger.warning("Chart generation failed: %s", e)

    # Coach narrative
    coach_narrative = _generate_weekly_coach_narrative(analysis, entries, age_years)

    # Milestone
    milestone_message = None
    if total_entries in [7, 14, 30, 60, 90]:
        milestone_message = f"Congratulations! You have logged {total_entries} sleep entries."

    # Next week goal
    if days_logged < 3:
        next_week_goal = "Log a few more nights this week to unlock better insights."
    elif analysis.average_duration < 7:
        next_week_goal = "Focus on getting at least 7 hours of sleep per night."
    else:
        next_week_goal = analysis.recommendations[0] if analysis.recommendations else "Maintain consistency in your sleep schedule."

    week_start = datetime.datetime.strptime(rows_sorted[0]["date"], "%Y-%m-%d").date()
    week_end = datetime.datetime.strptime(rows_sorted[-1]["date"], "%Y-%m-%d").date()

    return WeeklyReportSchema(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        analysis=analysis,
        plotly_chart_path=chart_path if chart_exists else None,
        milestone_message=milestone_message,
        next_week_goal=next_week_goal,
        coach_narrative=coach_narrative or None,
    )