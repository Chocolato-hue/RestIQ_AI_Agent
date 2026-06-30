"""Sleep pattern analysis shared by analyzer and reporter tools."""

from schemas import SleepAnalysisSchema, SleepEntrySchema, VerdictLabel


def build_sleep_analysis(
    user_id: str,
    period_days: int,
    entries: list[SleepEntrySchema],
    streak_days: int,
) -> SleepAnalysisSchema:
    scores = [e.score for e in entries]
    durations = [e.sleep_duration for e in entries]
    wake_ups = [e.wake_up_count for e in entries]

    average_score = sum(scores) / len(scores)
    average_duration = sum(durations) / len(durations)
    average_wake_ups = sum(wake_ups) / len(wake_ups)

    best_night = max(entries, key=lambda e: e.score)
    worst_night = min(entries, key=lambda e: e.score)

    patterns_detected: list[str] = []
    recommendations: list[str] = []

    caffeine_scores = [e.score for e in entries if e.caffeine_after_2pm]
    no_caffeine_scores = [e.score for e in entries if not e.caffeine_after_2pm]
    if caffeine_scores and no_caffeine_scores:
        diff = (sum(no_caffeine_scores) / len(no_caffeine_scores)) - (
            sum(caffeine_scores) / len(caffeine_scores)
        )
        if diff > 3:
            caffeine_impact = (
                f"Late caffeine consumption correlates with a {diff:.1f} point drop in sleep score."
            )
            patterns_detected.append("Caffeine after 2 PM impairs sleep quality.")
            recommendations.append("Limit caffeine intake to before 2:00 PM.")
        else:
            caffeine_impact = "No strong correlation detected between late caffeine and sleep scores."
    else:
        caffeine_impact = "Insufficient data to determine caffeine impact."

    screen_scores = [e.score for e in entries if e.screen_time_before_bed]
    no_screen_scores = [e.score for e in entries if not e.screen_time_before_bed]
    if screen_scores and no_screen_scores:
        diff = (sum(no_screen_scores) / len(no_screen_scores)) - (
            sum(screen_scores) / len(screen_scores)
        )
        if diff > 3:
            screen_time_impact = (
                f"Pre-bed screen time correlates with a {diff:.1f} point drop in sleep score."
            )
            patterns_detected.append("Blue light exposure before bed lowers sleep score.")
            recommendations.append("Implement a screen-free window 30-60 minutes before bedtime.")
        else:
            screen_time_impact = (
                "No strong correlation detected between pre-bed screen time and sleep scores."
            )
    else:
        screen_time_impact = "Insufficient data to determine screen time impact."

    exercise_scores = [e.score for e in entries if e.exercise_today]
    no_exercise_scores = [e.score for e in entries if not e.exercise_today]
    if exercise_scores and no_exercise_scores:
        diff = (sum(exercise_scores) / len(exercise_scores)) - (
            sum(no_exercise_scores) / len(no_exercise_scores)
        )
        if diff > 3:
            exercise_impact = (
                f"Daytime exercise correlates with a {diff:.1f} point increase in sleep score."
            )
            patterns_detected.append("Physical activity enhances overall sleep quality.")
            recommendations.append("Continue regular daily exercise to support rest.")
        else:
            exercise_impact = "No strong correlation detected between daily exercise and sleep scores."
    else:
        exercise_impact = "Insufficient data to determine exercise impact."

    if average_score < 50:
        verdict = VerdictLabel.NEEDS_ATTENTION
    elif average_score <= 65:
        verdict = VerdictLabel.IMPROVING
    elif average_score <= 80:
        verdict = VerdictLabel.ON_TRACK
    else:
        verdict = VerdictLabel.EXCELLENT

    if not patterns_detected:
        patterns_detected.append("Your sleep metrics are currently stable.")
    if not recommendations:
        recommendations.append("Maintain consistency in bedtime and waking hours.")

    return SleepAnalysisSchema(
        user_id=user_id,
        period_days=period_days,
        average_score=round(average_score, 1),
        average_duration=round(average_duration, 1),
        average_wake_ups=round(average_wake_ups, 1),
        best_night=best_night,
        worst_night=worst_night,
        patterns_detected=patterns_detected,
        recommendations=recommendations,
        verdict=verdict,
        streak_days=streak_days,
        caffeine_impact=caffeine_impact,
        exercise_impact=exercise_impact,
        screen_time_impact=screen_time_impact,
    )
