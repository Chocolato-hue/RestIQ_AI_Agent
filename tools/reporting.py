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

logger = logging.getLogger("tools.reporting")


def generate_report(user_id: str) -> WeeklyReportSchema:
    logger.info("[REPORTING] generate_report user_id=%s", user_id)

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT * FROM sleep_entries
        WHERE user_id = ?
        ORDER BY date DESC LIMIT 7
        """,
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
        raise ValueError(
            "No sleep entries found. Please log at least 3 nights of sleep first. "
            "Use /checkin in Telegram or the Check-in tab in the Streamlit dashboard."
        )

    if len(rows) < 3:
        raise ValueError(
            f"You only have {len(rows)} sleep entr{'y' if len(rows) == 1 else 'ies'} recorded. "
            "A minimum of 3 entries is required to generate a meaningful weekly report. "
            "Please log more sleep via /checkin in Telegram or the Check-in tab in the Streamlit dashboard."
        )

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    dates = [r["date"] for r in rows_sorted]

    entries = []
    scores = []
    for r in rows_sorted:
        entry = row_to_entry(r)
        if entry.score is None:
            entry.score = compute_sleep_score(entry)
        entries.append(entry)
        scores.append(entry.score)
    ensure_entry_scores(entries)

    import plotly.graph_objects as go
    import plotly.io as pio

    colors = []
    for s in scores:
        if s < 50:
            colors.append("#FF4B4B")
        elif s <= 75:
            colors.append("#FFAA00")
        else:
            colors.append("#00CC88")

    fig = go.Figure(
        data=[
            go.Bar(
                x=dates,
                y=scores,
                marker_color=colors,
                text=scores,
                textposition="auto",
            )
        ]
    )
    fig.update_layout(
        title="Weekly Sleep Scores",
        xaxis_title="Date",
        yaxis_title="Sleep Score",
        yaxis=dict(range=[0, 100]),
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    chart_path = f"/tmp/restiq_report_{user_id}.png"
    os.makedirs(os.path.dirname(chart_path), exist_ok=True)
    try:
        pio.write_image(fig, chart_path, engine="kaleido")
    except Exception as e_img:
        logger.warning(
            "[REPORTING] Plotly write_image failed (kaleido not available): %s. Writing mock file.",
            str(e_img),
        )
        with open(chart_path, "wb") as f:
            f.write(b"MOCK_PNG_DATA")

    analysis = build_sleep_analysis(user_id, 7, entries, check_in_streak)

    milestones = [7, 14, 30, 60, 90]
    milestone_message = None
    for m in milestones:
        if total_entries == m:
            milestone_message = (
                f"Congratulations! You have logged {m} sleep entries. "
                "You've reached a major tracking milestone!"
            )
            break
    if not milestone_message:
        for m in milestones:
            if check_in_streak == m:
                milestone_message = (
                    f"Wow! You've achieved a check-in streak of {m} days. Incredible consistency!"
                )
                break

    next_week_goal = "Aimed at improving sleep consistency: limit screen time 30 mins before sleep."
    if analysis.recommendations:
        next_week_goal = f"Focus on this recommendation: {analysis.recommendations[0]}"

    week_start = datetime.datetime.strptime(dates[0], "%Y-%m-%d").date()
    week_end = datetime.datetime.strptime(dates[-1], "%Y-%m-%d").date()

    return WeeklyReportSchema(
        user_id=user_id,
        week_start=week_start,
        week_end=week_end,
        analysis=analysis,
        plotly_chart_path=chart_path,
        milestone_message=milestone_message,
        next_week_goal=next_week_goal,
    )
