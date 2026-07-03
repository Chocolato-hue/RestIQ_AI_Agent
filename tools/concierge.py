"""Conversational sleep check-in concierge via Gemini."""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

from schemas import (
    ChatMessage,
    CheckinSessionState,
    ConciergeTurnResponse,
    PartialSleepSlots,
    REQUIRED_CHECKIN_SLOTS,
    SleepEntrySchema,
    SlotConfidence,
)

logger = logging.getLogger("tools.concierge")

_CONCIERGE_TEMPERATURE = 0.2

# LLM only extracts slots — follow-up questions are built in code (shorter, bundled).
_SYSTEM_INSTRUCTION = """You extract sleep check-in data from the user's latest message. You do NOT ask questions.

Return JSON only:
{
  "acknowledgment": "max 8 words mirroring something specific they said, or empty string",
  "updated_slots": {
    "bedtime": "HH:MM or null",
    "wake_time": "HH:MM or null",
    "wake_up_count": null,
    "sleep_quality": "POOR|FAIR|GOOD|EXCELLENT or null",
    "mood_on_wake": "TERRIBLE|TIRED|OKAY|GOOD|GREAT or null",
    "caffeine_after_2pm": null,
    "exercise_today": null,
    "screen_time_before_bed": null,
    "focus_level": null,
    "energy_level": null,
    "notes": null
  },
  "slot_confidence": {
    "bedtime": "known|inferred|unknown",
    "wake_time": "known|inferred|unknown",
    ...
  },
  "curiosity_note": "optional short note max 60 chars, or null"
}

Rules:
- Only update fields mentioned or clearly implied in THIS message.
- known = user stated it; inferred = reasonable from context; unknown = not addressed.
- If user denies caffeine/exercise/screens, set false with known confidence.
- If user says uninterrupted/straight through/slept through, wake_up_count=0 known.
- Fuzzy times ("around 3am"): pick best HH:MM as inferred, not unknown.
- "Slept fine/okay/sufficient" → sleep_quality FAIR or GOOD inferred, mood_on_wake OKAY inferred.
- curiosity_note: one short fact only, no quotes inside the string.
- acknowledgment: empty string if nothing new to mirror. Never write paragraphs.
"""


class _ConciergeLLMResponse(BaseModel):
    acknowledgment: str = ""
    updated_slots: PartialSleepSlots = Field(default_factory=PartialSleepSlots)
    slot_confidence: dict[str, str] = Field(default_factory=dict)
    curiosity_note: Optional[str] = None


def _memory_context_from_entry(latest_entry: Optional[SleepEntrySchema]) -> Optional[str]:
    if not latest_entry:
        return None
    if latest_entry.screen_time_before_bed:
        return "screens were the focus yesterday."
    if latest_entry.caffeine_after_2pm:
        return "caffeine was the focus yesterday."
    if latest_entry.wake_up_count > 1:
        return "wake-ups were rough yesterday."
    if latest_entry.sleep_duration < 7:
        return "short sleep yesterday."
    if latest_entry.score and latest_entry.score >= 85:
        return "great score yesterday."
    return None


def _default_opener(session_context: Optional[str]) -> str:
    if session_context:
        return f"Morning 🌙 ({session_context}) What happened with your sleep last night?"
    return "Morning 🌙 What happened with your sleep last night?"


def start_session(
    user_id: str,
    latest_entry: Optional[SleepEntrySchema] = None,
    session_context: Optional[str] = None,
    include_opener: bool = True,
) -> tuple[CheckinSessionState, str]:
    """Create a new check-in session and return its opening message."""
    context = session_context or _memory_context_from_entry(latest_entry)
    session = CheckinSessionState(user_id=user_id, session_context=context)
    opener = _default_opener(context)
    if include_opener:
        session.messages.append(ChatMessage(role="assistant", content=opener))
    return session, opener


def _serialize_session_for_prompt(session: CheckinSessionState) -> str:
    slots = session.slots.model_dump(exclude_none=True)
    confidence = {k: v.value for k, v in session.slot_confidence.items()}
    history = "\n".join(
        f"{'User' if m.role == 'user' else 'RestIQ'}: {m.content}"
        for m in session.messages
    )
    return (
        f"Already collected: {json.dumps(slots)}\n"
        f"Confidence: {json.dumps(confidence)}\n"
        f"Still unknown: {session.missing_slots()}\n"
        f"Chat:\n{history}"
    )


def _normalize_confidence(raw: dict[str, str]) -> dict[str, SlotConfidence]:
    result: dict[str, SlotConfidence] = {}
    for key, val in raw.items():
        try:
            result[key] = SlotConfidence(str(val).lower())
        except ValueError:
            result[key] = SlotConfidence.UNKNOWN
    return result


def _parse_llm_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _merge_slots(session: CheckinSessionState, turn: ConciergeTurnResponse) -> None:
    updates = turn.updated_slots.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(session.slots, key, value)
    for key, conf in turn.slot_confidence.items():
        if key not in REQUIRED_CHECKIN_SLOTS and key not in ("focus_level", "energy_level"):
            continue
        existing = session.slot_confidence.get(key, SlotConfidence.UNKNOWN)
        # Never downgrade a slot we already know
        if conf == SlotConfidence.UNKNOWN and existing != SlotConfidence.UNKNOWN:
            continue
        session.slot_confidence[key] = conf
    if turn.curiosity_note:
        note = turn.curiosity_note[:120].strip()
        session.curiosity_notes.append(note)
        existing = session.slots.notes or ""
        session.slots.notes = f"{existing} {note}".strip()


def _build_follow_up(session: CheckinSessionState) -> Optional[str]:
    """Short, bundled follow-ups — avoids one long LLM question per slot."""
    missing = session.missing_slots()
    if not missing:
        return None

    slots = session.slots
    conf = session.slot_confidence

    if "bedtime" in missing and "wake_time" in missing:
        return "What time did you go to bed and wake up?"
    if "bedtime" in missing:
        return "What time did you get to bed?"
    if "wake_time" in missing:
        return "What time did you wake up?"

    if "wake_up_count" in missing:
        return "Any wake-ups during the night?"

    habit_keys = ("caffeine_after_2pm", "exercise_today", "screen_time_before_bed")
    habit_missing = [h for h in habit_keys if h in missing]
    if habit_missing:
        labels = {
            "caffeine_after_2pm": "caffeine after 2pm",
            "exercise_today": "exercise",
            "screen_time_before_bed": "screens before bed",
        }
        # Skip habits already denied
        habit_missing = [
            h for h in habit_missing
            if not (conf.get(h) == SlotConfidence.KNOWN and getattr(slots, h) is False)
        ]
        if not habit_missing:
            pass
        elif len(habit_missing) >= 2:
            parts = [labels[h] for h in habit_missing]
            return f"Quick habits check — any {' / '.join(parts)}?"
        else:
            return f"Any {labels[habit_missing[0]]}?"

    if "sleep_quality" in missing and "mood_on_wake" in missing:
        return "How was the sleep, and how did you feel waking up?"
    if "sleep_quality" in missing:
        return "Rough, okay, or good sleep overall?"
    if "mood_on_wake" in missing:
        return "How did you feel when you woke up?"

    return None


def _format_reply(acknowledgment: str, follow_up: Optional[str], *, complete: bool = False) -> str:
    ack = acknowledgment.strip()
    if len(ack.split()) > 10:
        ack = ""

    if complete:
        base = ack or "Got it."
        return f"{base} Ready to analyze whenever you are."

    if not follow_up:
        return ack or "Got it."

    if ack:
        return f"{ack} {follow_up}"
    return follow_up


def _call_concierge(session: CheckinSessionState, user_message: str) -> ConciergeTurnResponse:
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GOOGLE_API_KEY is not set. Add it to your .env file — "
            "get a free key at https://aistudio.google.com/apikey"
        )

    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    prompt = (
        f"{_serialize_session_for_prompt(session)}\n\n"
        f"Latest user message: {user_message}\n\n"
        "Extract slots from the latest message only."
    )

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=_CONCIERGE_TEMPERATURE,
        ),
    )

    try:
        parsed = _parse_llm_json(response.text)
        llm = _ConciergeLLMResponse(**parsed)
    except Exception as e:
        logger.error("Concierge JSON parse failed: %s | raw=%s", e, response.text[:500])
        raise ValueError(
            "Had trouble reading that — try sending again in one short line."
        ) from e

    confidence = _normalize_confidence(llm.slot_confidence)

    return ConciergeTurnResponse(
        acknowledgment=llm.acknowledgment,
        updated_slots=llm.updated_slots,
        slot_confidence=confidence,
        follow_up=None,
        is_complete=False,
        curiosity_note=llm.curiosity_note,
    )


def process_turn(session: CheckinSessionState, user_message: str) -> tuple[CheckinSessionState, str]:
    """Process one user message and return updated session plus agent reply text."""
    user_message = user_message.strip()
    if not user_message:
        raise ValueError("User message cannot be empty.")

    session.messages.append(ChatMessage(role="user", content=user_message))
    turn = _call_concierge(session, user_message)
    _merge_slots(session, turn)

    # Default focus/energy without asking
    for field in ("focus_level", "energy_level"):
        if field not in session.slot_confidence:
            setattr(session.slots, field, 3)
            session.slot_confidence[field] = SlotConfidence.INFERRED

    is_complete = session.is_complete()
    follow_up = None if is_complete else _build_follow_up(session)

    reply = _format_reply(turn.acknowledgment, follow_up, complete=is_complete)
    session.messages.append(ChatMessage(role="assistant", content=reply))
    return session, reply


def build_transcript(session: CheckinSessionState) -> str:
    """Build a rich transcript for final intake parsing."""
    lines = []
    if session.session_context:
        lines.append(f"Context: {session.session_context}")
    for msg in session.messages:
        prefix = "User" if msg.role == "user" else "RestIQ"
        lines.append(f"{prefix}: {msg.content}")
    slots = session.slots.model_dump(exclude_none=True)
    if slots:
        lines.append(f"Collected slots summary: {json.dumps(slots)}")
    if session.curiosity_notes:
        lines.append(f"Additional notes: {'; '.join(session.curiosity_notes)}")
    return "\n".join(lines)


def session_from_dict(data: dict) -> CheckinSessionState:
    """Deserialize session from a plain dict (e.g. Telegram user_data)."""
    slot_conf = {
        k: SlotConfidence(v) if not isinstance(v, SlotConfidence) else v
        for k, v in data.get("slot_confidence", {}).items()
    }
    messages = [ChatMessage(**m) for m in data.get("messages", [])]
    slots = PartialSleepSlots(**data.get("slots", {}))
    return CheckinSessionState(
        user_id=data["user_id"],
        messages=messages,
        slots=slots,
        slot_confidence=slot_conf,
        session_context=data.get("session_context"),
        curiosity_notes=data.get("curiosity_notes", []),
    )


def session_to_dict(session: CheckinSessionState) -> dict:
    """Serialize session for storage (e.g. Telegram user_data)."""
    return {
        "user_id": session.user_id,
        "messages": [m.model_dump() for m in session.messages],
        "slots": session.slots.model_dump(exclude_none=True),
        "slot_confidence": {k: v.value for k, v in session.slot_confidence.items()},
        "session_context": session.session_context,
        "curiosity_notes": session.curiosity_notes,
    }
