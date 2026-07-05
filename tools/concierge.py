"""Conversational sleep check-in concierge via Gemini.

Changes vs. original:
 - Fix A+B: age collected then session continues to sleep slots immediately;
   non-numeric / impossible age handled with attempt counting (cap = 2).
 - Coach narrative generated in the SAME LLM call as slot extraction
   (extended JSON schema, no extra API round-trip).
 - session_to_dict / session_from_dict now carry age_attempt_count and
   coach_narrative so they survive Streamlit reruns.
"""

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
_AGE_MAX_ATTEMPTS = 2

# ---------------------------------------------------------------------------
# System instruction – coach persona, slot extraction + coach narrative
# ---------------------------------------------------------------------------
_SYSTEM_INSTRUCTION = """You are RestIQ, a warm and encouraging sleep coach.

The user is {age_info} years old.

Your job is to collect complete sleep data through natural conversation.

Return **ONLY valid JSON**. No extra text, no markdown, no explanations.

JSON format:
{
  "acknowledgment": "short personal reply (max 12 words)",
  "updated_slots": {
    "bedtime": "HH:MM or null",
    "wake_time": "HH:MM or null",
    "wake_up_count": number or null,
    "sleep_quality": "POOR|FAIR|GOOD|EXCELLENT or null",
    "mood_on_wake": "TERRIBLE|TIRED|OKAY|GOOD|GREAT or null",
    "caffeine_after_2pm": true/false or null,
    "exercise_today": true/false or null,
    "screen_time_before_bed": true/false or null,
    "focus_level": 1-5 or null,
    "energy_level": 1-5 or null,
    "notes": "short summary or null"
  },
  "slot_confidence": {
    "bedtime": "known|inferred|unknown",
    "wake_time": "known|inferred|unknown",
    "wake_up_count": "known|inferred|unknown",
    "sleep_quality": "known|inferred|unknown",
    "mood_on_wake": "known|inferred|unknown",
    "caffeine_after_2pm": "known|inferred|unknown",
    "exercise_today": "known|inferred|unknown",
    "screen_time_before_bed": "known|inferred|unknown",
    "focus_level": "known|inferred|unknown",
    "energy_level": "known|inferred|unknown"
  },
  "curiosity_note": "optional short note or null"
}

Strict Rules:
- If user says "2 am and 9 am" → bedtime="02:00", wake_time="09:00", confidence="known"
- If user says "slept at 11pm, woke at 7am" → bedtime="23:00", wake_time="07:00"
- Always use 24-hour format (HH:MM) for times.
- Only fill slots that are clearly mentioned or strongly implied.
- Never repeat the same question if the slot is already "known".
- After getting age, immediately ask about bedtime/wake time.
- If the user message is empty, nonsensical, or off-topic, respond with a gentle nudge back to sleep discussion.
- Keep responses short and natural.
"""

class _ConciergeLLMResponse(BaseModel):
    acknowledgment: str = ""
    updated_slots: PartialSleepSlots = Field(default_factory=PartialSleepSlots)
    slot_confidence: dict[str, str] = Field(default_factory=dict)
    curiosity_note: Optional[str] = None
    coach_narrative: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _age_from_message(text: str) -> Optional[float]:
    """Try to parse a plain number from a user message as age."""
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        val = float(match.group(1))
        if 1 <= val <= 120:
            return val
    return None


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------

def start_session(
    user_id: str,
    latest_entry: Optional[SleepEntrySchema] = None,
    session_context: Optional[str] = None,
    include_opener: bool = True,
    age_years: Optional[float] = None,
) -> tuple[CheckinSessionState, str]:
    """Create a new check-in session."""
    context = session_context or _memory_context_from_entry(latest_entry)

    session = CheckinSessionState(
        user_id=user_id,
        session_context=context,
        age_years=age_years,
    )

    from datetime import datetime
    hour = datetime.now().hour
    if 5 <= hour < 12:
        greeting = "Good morning"
    elif 12 <= hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    opener = f"{greeting} 🌙 What happened with your sleep last night?"
    if context:
        opener = f"{greeting} 🌙 ({context}) What happened with your sleep last night?"

    if include_opener:
        session.messages.append(ChatMessage(role="assistant", content=opener))

    return session, opener


def _serialize_session_for_prompt(session: CheckinSessionState) -> str:
    slots = session.slots.model_dump(exclude_none=True)
    confidence = {k: v.value for k, v in session.slot_confidence.items()}
    age_info = (
        f"User is {session.age_years:.0f} years old."
        if session.age_years
        else "User age unknown."
    )
    history = "\n".join(
        f"{'User' if m.role == 'user' else 'RestIQ'}: {m.content}"
        for m in session.messages
    )
    return (
        f"{age_info}\n"
        f"Already collected: {json.dumps(slots)}\n"
        f"Confidence: {json.dumps(confidence)}\n"
        f"Still missing: {session.missing_slots()}\n"
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
    """Robust JSON parser for Gemini responses."""
    text = raw.strip()
    
    # Remove markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON object if there's extra text
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                json_str = text[start : end + 1]
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        # Last resort: try to fix common issues
        try:
            # Remove any trailing text after last }
            text = text[:text.rfind("}") + 1]
            return json.loads(text)
        except:
            raise ValueError(f"Failed to parse AI response as JSON. Raw: {raw[:300]}...")


def _merge_slots(session: CheckinSessionState, turn: ConciergeTurnResponse) -> None:
    updates = turn.updated_slots.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(session.slots, key, value)
        
        # IMPORTANT: Mark as KNOWN when we receive a value
        if value is not None:
            session.slot_confidence[key] = SlotConfidence.KNOWN
    for key, conf in turn.slot_confidence.items():
        if key not in REQUIRED_CHECKIN_SLOTS and key not in ("focus_level", "energy_level"):
            continue
        existing = session.slot_confidence.get(key, SlotConfidence.UNKNOWN)
        if conf == SlotConfidence.UNKNOWN and existing != SlotConfidence.UNKNOWN:
            continue
        session.slot_confidence[key] = conf
    if turn.curiosity_note:
        note = turn.curiosity_note[:120].strip()
        session.curiosity_notes.append(note)
        existing = session.slots.notes or ""
        session.slots.notes = f"{existing} {note}".strip()


# ---------------------------------------------------------------------------
# Age handling (Fix A + B)
# ---------------------------------------------------------------------------

def _handle_age_turn(session: CheckinSessionState, user_message: str) -> Optional[str]:
    """
    Handle the age collection phase. Returns a follow-up string if we are
    still waiting for age, or None if age is resolved (and the caller should
    move on to sleep-slot questions).

    Fix A: After age is given, returns None → caller continues normally.
    Fix B: Validates numeric + plausible; after 2 failed attempts gives up.
    """
    # Age already known — nothing to do
    if session.age_years is not None and session.age_years > 0:
        return None

    # Haven't asked yet → ask once
    if not session.age_asked:
        session.age_asked = True
        return (
            "To give you the most personalized advice, "
            "could you share your age? (Just the number 😊)"
        )

    # Already asked — try to parse the current reply
    parsed = _age_from_message(user_message)

    if parsed is not None:
        session.age_years = parsed
        return None  # ✅ age captured → continue to sleep questions

    # Bad answer — count the attempt
    session.age_attempt_count += 1

    if session.age_attempt_count >= _AGE_MAX_ATTEMPTS:
        # Give up gracefully — proceed without age
        logger.info("[CONCIERGE] Max age attempts reached; proceeding without age.")
        session.age_years = None  # explicitly None so we stop asking
        session.age_asked = True
        return None

    # Detect impossible-looking number
    big_num = re.search(r"\b(\d{3,})\b", user_message)
    if big_num and int(big_num.group(1)) > 120:
        return "That age seems off — could you double-check? I just need a number between 1 and 120. 😊"

    return (
        "Got it — but I need a specific number. "
        "Could you tell me your exact age in years?"
    )


# ---------------------------------------------------------------------------
# Follow-up question builder
# ---------------------------------------------------------------------------

def _build_follow_up(session: CheckinSessionState) -> Optional[str]:
    """Build the next contextual question for missing sleep slots."""
    missing = session.missing_slots()
    if not missing:
        return "All set! Click **Analyze my sleep** below when ready."

    asked_bedtime = session.slot_confidence.get("bedtime") == SlotConfidence.KNOWN
    asked_wake = session.slot_confidence.get("wake_time") == SlotConfidence.KNOWN

    if not asked_bedtime and not asked_wake:
        return "What time did you go to bed and wake up last night?"
    if not asked_bedtime:
        return "What time did you get to bed?"
    if not asked_wake:
        return "What time did you wake up?"

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
            "caffeine_after_2pm": "caffeine after 2 pm",
            "exercise_today": "exercise",
            "screen_time_before_bed": "screens before bed",
        }
        habit_missing = [
            h for h in habit_missing
            if not (conf.get(h) == SlotConfidence.KNOWN and getattr(slots, h) is False)
        ]
        if habit_missing:
            if len(habit_missing) >= 2:
                parts = [labels[h] for h in habit_missing]
                return f"Quick habits check — any {' / '.join(parts)}?"
            return f"Any {labels[habit_missing[0]]}?"

    if "sleep_quality" in missing and "mood_on_wake" in missing:
        return "How was the sleep overall, and how did you feel waking up?"
    if "sleep_quality" in missing:
        return "Rough, okay, or good sleep overall?"
    if "mood_on_wake" in missing:
        return "How did you feel when you woke up?"

    return None


def _format_reply(acknowledgment: str, follow_up: Optional[str], *, complete: bool = False) -> str:
    ack = acknowledgment.strip()
    if len(ack.split()) > 12:
        ack = ""

    if complete:
        base = ack or "Got it."
        return f"{base} Ready to analyze whenever you are."

    if not follow_up:
        return ack or "Got it."

    if ack:
        return f"{ack} {follow_up}"
    return follow_up


# ---------------------------------------------------------------------------
# LLM call (slot extraction + coach narrative in one request)
# ---------------------------------------------------------------------------

def _call_concierge(session: CheckinSessionState, user_message: str) -> _ConciergeLLMResponse:
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

    age_info = (
        f"{session.age_years:.0f}"
        if session.age_years
        else "unknown"
    )
    is_complete_after = session.is_complete() or (
        len(session.missing_slots()) <= 1
    )

    prompt = (
        f"{_serialize_session_for_prompt(session)}\n\n"
        f"Latest user message: {user_message}\n\n"
        f"Session complete after this turn: {is_complete_after}\n"
        "Extract slots from the latest message only. "
        "If session_complete is True, also write coach_narrative."
    )

    system = _SYSTEM_INSTRUCTION.replace("{age_info}", age_info)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=_CONCIERGE_TEMPERATURE,
        ),
    )

    try:
        parsed = _parse_llm_json(response.text)
        llm = _ConciergeLLMResponse(**parsed)
    except Exception as e:
        logger.error("JSON parse failed: %s", e)
        raise ValueError("Had trouble reading that — try sending again.") from e

    return llm


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def process_turn(session: CheckinSessionState, user_message: str) -> tuple[CheckinSessionState, str]:
    """Process one user message and return updated session + agent reply text."""
    user_message = user_message.strip()
    if not user_message:
        raise ValueError("User message cannot be empty.")

    session.messages.append(ChatMessage(role="user", content=user_message))

    # --- Age collection phase (Fix A + B) ---
    age_reply = _handle_age_turn(session, user_message)
    if age_reply is not None:
        # Still resolving age — don't run full LLM call
        session.messages.append(ChatMessage(role="assistant", content=age_reply))
        return session, age_reply

    # --- Normal slot-extraction phase ---
    llm = _call_concierge(session, user_message)

    # Map _ConciergeLLMResponse → ConciergeTurnResponse for _merge_slots
    confidence = _normalize_confidence(llm.slot_confidence)
    turn = ConciergeTurnResponse(
        acknowledgment=llm.acknowledgment,
        updated_slots=llm.updated_slots,
        slot_confidence=confidence,
        follow_up=None,
        is_complete=False,
        curiosity_note=llm.curiosity_note,
    )
    _merge_slots(session, turn)

    # Silently fill focus/energy so they never block completion
    for field in ("focus_level", "energy_level"):
        if field not in session.slot_confidence:
            setattr(session.slots, field, 3)
            session.slot_confidence[field] = SlotConfidence.INFERRED

    # Store coach narrative if the LLM generated one
    if llm.coach_narrative and llm.coach_narrative.strip():
        session.coach_narrative = llm.coach_narrative.strip()

    is_complete = session.is_complete()
    follow_up = None if is_complete else _build_follow_up(session)

    reply = _format_reply(llm.acknowledgment, follow_up, complete=is_complete)
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
    """Deserialize session from a plain dict (e.g. Telegram user_data or st.session_state)."""
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
        age_years=data.get("age_years"),
        age_asked=data.get("age_asked", False),
        age_attempt_count=data.get("age_attempt_count", 0),
        coach_narrative=data.get("coach_narrative"),
    )


def session_to_dict(session: CheckinSessionState) -> dict:
    """Serialize session for storage (e.g. Telegram user_data or st.session_state)."""
    return {
        "user_id": session.user_id,
        "messages": [m.model_dump() for m in session.messages],
        "slots": session.slots.model_dump(exclude_none=True),
        "slot_confidence": {k: v.value for k, v in session.slot_confidence.items()},
        "session_context": session.session_context,
        "curiosity_notes": session.curiosity_notes,
        "age_years": session.age_years,
        "age_asked": session.age_asked,
        "age_attempt_count": session.age_attempt_count,
        "coach_narrative": session.coach_narrative,
    }
