"""Natural-language sleep intake via Gemini."""

import json
import logging
import os
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from schemas import MoodOnWake, SleepEntrySchema, SleepQuality

from services.scoring import calculate_duration

logger = logging.getLogger("services.intake")


class SleepExtractionSchema(BaseModel):
    bedtime: str = Field(..., description="Bedtime in HH:MM format (24-hour clock)")
    wake_time: str = Field(..., description="Wake time in HH:MM format (24-hour clock)")
    wake_up_count: int = Field(..., ge=0, le=10)
    sleep_quality: SleepQuality
    mood_on_wake: MoodOnWake
    caffeine_after_2pm: bool
    exercise_today: bool
    screen_time_before_bed: bool
    focus_level: int = Field(..., ge=1, le=5)
    energy_level: int = Field(..., ge=1, le=5)
    notes: Optional[str] = None


_SYSTEM_INSTRUCTION = (
    "You are an expert sleep data extraction assistant.\n"
    "Analyze the user's natural language check-in text and extract structured sleep information.\n"
    "Strictly extract all required fields and return ONLY a valid JSON object matching the following structure.\n"
    "Do NOT wrap the response in markdown code blocks. The response must be pure JSON.\n"
    "{\n"
    '  "bedtime": "HH:MM",\n'
    '  "wake_time": "HH:MM",\n'
    '  "wake_up_count": 0,\n'
    '  "sleep_quality": "GOOD",\n'
    '  "mood_on_wake": "OKAY",\n'
    '  "caffeine_after_2pm": false,\n'
    '  "exercise_today": false,\n'
    '  "screen_time_before_bed": false,\n'
    '  "focus_level": 3,\n'
    '  "energy_level": 3,\n'
    '  "notes": null\n'
    "}\n"
    "If any value is not explicitly mentioned, estimate it reasonably based on context or use standard sensible defaults:\n"
    "- bedtime & wake_time: HH:MM format (24-hour clock)\n"
    "- wake_up_count: integer (0-10)\n"
    "- sleep_quality: POOR, FAIR, GOOD, or EXCELLENT\n"
    "- mood_on_wake: TERRIBLE, TIRED, OKAY, GOOD, or GREAT\n"
    "- caffeine_after_2pm, exercise_today, screen_time_before_bed: boolean\n"
    "- focus_level: integer 1-5. Only infer from explicit statements about concentration. If none, use 3.\n"
    "- energy_level: integer 1-5. Only infer from explicit statements about tiredness. If none, use 3.\n"
    "- notes: str or null"
)


def parse_sleep_input(user_id: str, raw_text: str) -> SleepEntrySchema:
    logger.info("[INTAKE] parse_sleep_input user_id=%s", user_id)
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is not set.")

    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    response = client.models.generate_content(
        model=model_name,
        contents=raw_text,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )

    try:
        parsed_json = json.loads(response.text)
        extracted = SleepExtractionSchema(**parsed_json)
    except Exception as e:
        raise ValueError(
            f"Failed to parse structured output from Gemini. Error: {e}. Raw text: {response.text}"
        ) from e

    duration = calculate_duration(extracted.bedtime, extracted.wake_time)

    return SleepEntrySchema(
        user_id=user_id,
        date=date.today(),
        bedtime=extracted.bedtime,
        wake_time=extracted.wake_time,
        sleep_duration=duration,
        wake_up_count=extracted.wake_up_count,
        sleep_quality=extracted.sleep_quality,
        mood_on_wake=extracted.mood_on_wake,
        caffeine_after_2pm=extracted.caffeine_after_2pm,
        exercise_today=extracted.exercise_today,
        screen_time_before_bed=extracted.screen_time_before_bed,
        focus_level=extracted.focus_level,
        energy_level=extracted.energy_level,
        notes=extracted.notes,
        score=None,
    )
