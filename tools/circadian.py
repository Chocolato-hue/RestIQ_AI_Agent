"""Circadian schedule recommendations."""

import logging

from schemas import CircadianSchema

logger = logging.getLogger("tools.circadian")


def calculate_circadian(wake_time: str, sleep_duration: float = 8.0) -> CircadianSchema:
    logger.info(
        "[CIRCADIAN] wake_time=%s sleep_duration=%s", wake_time, sleep_duration
    )
    h, m = map(int, wake_time.split(":"))
    wake_minutes = h * 60 + m

    bedtime_minutes = int(wake_minutes - (sleep_duration * 60)) % (24 * 60)
    wind_down_minutes = (bedtime_minutes - 15) % (24 * 60)

    recommended_bedtime = f"{bedtime_minutes // 60:02d}:{bedtime_minutes % 60:02d}"
    recommended_wake_time = f"{h:02d}:{m:02d}"
    wind_down_start = f"{wind_down_minutes // 60:02d}:{wind_down_minutes % 60:02d}"

    return CircadianSchema(
        recommended_bedtime=recommended_bedtime,
        recommended_wake_time=recommended_wake_time,
        sleep_window_hours=float(sleep_duration),
        wind_down_start=wind_down_start,
        notes=(
            f"To wake up rested at {recommended_wake_time} with {sleep_duration} hours of sleep, "
            f"aim to sleep by {recommended_bedtime} and start winding down at {wind_down_start}."
        ),
    )
