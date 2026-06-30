"""Sleep duration and score calculations."""

from schemas import SleepEntrySchema, SleepQuality


def calculate_duration(bedtime_str: str, wake_time_str: str) -> float:
    """Calculates sleep duration in hours from bedtime to wake_time handling midnight wrap."""
    try:
        bt_h, bt_m = map(int, bedtime_str.split(":"))
        wt_h, wt_m = map(int, wake_time_str.split(":"))
        bt_total = bt_h + bt_m / 60.0
        wt_total = wt_h + wt_m / 60.0
        if wt_total >= bt_total:
            duration = wt_total - bt_total
        else:
            duration = (wt_total + 24.0) - bt_total
        return round(duration, 2)
    except Exception as e:
        raise ValueError(
            f"Failed to calculate sleep duration from bedtime '{bedtime_str}' "
            f"and wake_time '{wake_time_str}': {e}"
        ) from e


def compute_sleep_score(entry: SleepEntrySchema) -> int:
    """Computes a baseline sleep score from 0 to 100 based on habits and sleep details."""
    score = 100

    duration = entry.sleep_duration
    if duration < 7.0:
        score -= int((7.0 - duration) * 15)
    elif duration > 9.0:
        score -= int((duration - 9.0) * 10)

    score -= entry.wake_up_count * 8

    quality_map = {
        SleepQuality.POOR: -30,
        SleepQuality.FAIR: -10,
        SleepQuality.GOOD: 5,
        SleepQuality.EXCELLENT: 15,
    }
    score += quality_map.get(entry.sleep_quality, 0)

    if entry.screen_time_before_bed:
        score -= 15
    if entry.caffeine_after_2pm:
        score -= 10
    if entry.exercise_today:
        score += 10

    return max(0, min(100, score))
