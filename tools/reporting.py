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
            "No sleep entries found.\n\n"
            "Please log your sleep using /checkin before generating a weekly report."
        )

    if len(rows) < 3:
        raise ValueError(
            f"Not enough sleep data yet ({len(rows)}/3 nights).\n\n"
            "Please log at least 3 nights of sleep before generating a weekly report."
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

    day_labels = []
    for d in dates:
        try:
            day_labels.append(datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%a"))
        except Exception:
            day_labels.append(str(d))

    colors = []
    for s in scores:
        if s < 50:
            colors.append("#EF4444")
        elif s <= 75:
            colors.append("#F59E0B")
        else:
            colors.append("#10B981")

    fig = go.Figure(
        data=[
            go.Bar(
                x=day_labels,
                y=scores,
                marker_color=colors,
                text=[f"{s}/100" for s in scores],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Sleep Score: %{y}/100<extra></extra>",
            )
        ]    
    )

    fig.update_layout(
        title={
            "text": "Weekly Sleep Score",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Day",
        yaxis_title="Score",
        yaxis=dict(range=[0, 105]),
        width=900,
        height=520,
        margin=dict(l=70, r=40, t=80, b=70),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(size=18, color="#111827"),
        showlegend=False,
    )

    fig.update_xaxes(
        tickfont=dict(size=18),
        showgrid=False,
    )

    fig.update_yaxes(
        tickfont=dict(size=16),
        gridcolor="#E5E7EB",
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
