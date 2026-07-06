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

        FALLBACK_MODELS = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
        ]

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

        last_error = None
        for model_name in FALLBACK_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are RestIQ, a warm and encouraging sleep coach.",
                        temperature=0.4,
                    ),
                )
                break
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    last_error = e
                    continue
                raise
        else:
            raise last_error
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

    # Next week goal with smart personalization
    if days_logged < 3:
        next_week_goal = "Log a few more nights this week to unlock better insights."
    else:
        # 1. Check duration first (most important)
        if analysis.average_duration < 7:
            next_week_goal = (
                f"⏰ You're averaging {analysis.average_duration:.1f} hours of sleep. "
                f"Try going to bed **20–30 minutes earlier** to reach at least 7 hours. "
                f"Consistent sleep duration is the strongest predictor of recovery."
            )
        else:
            # 2. Duration is fine → check bedtime
            bedtimes = []
            for e in entries:
                if e.bedtime:
                    try:
                        bedtimes.append(datetime.strptime(e.bedtime, "%H:%M"))
                    except:
                        pass
            
            if bedtimes:
                avg_bedtime = sum([dt.hour * 60 + dt.minute for dt in bedtimes]) / len(bedtimes)
                avg_hour = avg_bedtime // 60
                avg_min = avg_bedtime % 60
                
                if 22 <= avg_hour <= 23:
                    # Already in ideal window → praise + next focus
                    if analysis.average_wake_ups > 1:
                        next_week_goal = "✅ Great bedtime! This week, focus on reducing wake-ups with a calm wind-down routine."
                    else:
                        next_week_goal = "🌟 Excellent sleep habits! Keep your consistent schedule going."
                else:
                    # Suggest shifting to ideal window
                    next_week_goal = (
                        f"💡 Try shifting your bedtime to between **10:00 PM and 11:00 PM** "
                        f"(you're currently averaging {int(avg_hour)}:{int(avg_min):02d} PM). "
                        "This aligns with your natural circadian rhythm for deeper sleep."
                    )
            else:
                # No bedtime data → generic
                next_week_goal = (
                    "💡 Aim to fall asleep between **10:00 PM and 11:00 PM** for optimal circadian alignment. "
                    "This window maximizes melatonin and deep sleep quality."
                )

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