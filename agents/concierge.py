"""Concierge agent wrapper for conversational check-in sessions."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional

from schemas import CheckinSessionState, SleepEntrySchema
from tools import concierge as concierge_tool


def start_session(
    user_id: str,
    latest_entry: Optional[SleepEntrySchema] = None,
    session_context: Optional[str] = None,
    include_opener: bool = True,
) -> tuple[CheckinSessionState, str]:
    return concierge_tool.start_session(user_id, latest_entry, session_context, include_opener)


def process_turn(session: CheckinSessionState, user_message: str) -> tuple[CheckinSessionState, str]:
    return concierge_tool.process_turn(session, user_message)


def build_transcript(session: CheckinSessionState) -> str:
    return concierge_tool.build_transcript(session)


def is_complete(session: CheckinSessionState) -> bool:
    return session.is_complete()


def session_from_dict(data: dict) -> CheckinSessionState:
    return concierge_tool.session_from_dict(data)


def session_to_dict(session: CheckinSessionState) -> dict:
    return concierge_tool.session_to_dict(session)
