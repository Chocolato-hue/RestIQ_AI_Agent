"""
schemas.py — RestIQ Sleep Concierge Agent
Pydantic data models for the Sleep Concierge multi-agent system.
"""

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────

class SleepQuality(str, Enum):
    """Quality of sleep rating."""
    POOR = "POOR"
    FAIR = "FAIR"
    GOOD = "GOOD"
    EXCELLENT = "EXCELLENT"


class MoodOnWake(str, Enum):
    """Mood upon waking up."""
    TERRIBLE = "TERRIBLE"
    TIRED = "TIRED"
    OKAY = "OKAY"
    GOOD = "GOOD"
    GREAT = "GREAT"


class VerdictLabel(str, Enum):
    """Overall sleep health verdict label."""
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    IMPROVING = "IMPROVING"
    ON_TRACK = "ON_TRACK"
    EXCELLENT = "EXCELLENT"


class CaffeineSensitivity(str, Enum):
    """Caffeine sensitivity level of the user."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PlanStatus(str, Enum):
    """Direction of the user's sleep trend relative to their current plan."""
    IMPROVING = "IMPROVING"
    DECLINING = "DECLINING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class PlanTrigger(str, Enum):
    """Which evaluation rule caused a plan adjustment to fire."""
    ROLLING_TREND = "ROLLING_TREND"
    WEEKLY_COMPARISON = "WEEKLY_COMPARISON"
    STREAK_OVERRIDE = "STREAK_OVERRIDE"
    NONE = "NONE"


class SlotConfidence(str, Enum):
    """How confidently a sleep slot was filled during conversational intake."""
    KNOWN = "known"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────

class SleepEntrySchema(BaseModel):
    """
    Represents a structured sleep log entry for a single night.

    Used by:
    - Intake Agent: To validate and format the user's daily check-in input.
    - Analyzer Agent: To parse historical logs and compute sleep scores and trends.

    MCP Tool connections:
    - SleepDatabaseMCP: Connects to `save_sleep_entry` (to record new entries) and
      `get_sleep_entries` (to fetch historical data for analysis).

    Note: populate_by_name=True lets this model accept either the field name
    ('entry_date') or its alias ('date') on input. This matters because
    model_dump(mode="json") (without by_alias=True) serializes using the field
    name, while the SQLite layer and MCP tool payloads use 'date'. Without this,
    round-tripping an instance through dict -> model again raises a validation
    error on a field that's actually present, just under the "wrong" key.
    """
    model_config = {"populate_by_name": True}

    user_id: str = Field(..., description="Unique identifier for the user")
    entry_date: date = Field(alias="date", description="The morning date when sleep log was recorded")
    bedtime: str = Field(..., description="Bedtime in HH:MM format (24-hour clock)")
    wake_time: str = Field(..., description="Wake time in HH:MM format (24-hour clock)")
    sleep_duration: float = Field(..., description="Calculated sleep duration in hours")
    wake_up_count: int = Field(..., ge=0, le=10, description="Number of wake-ups during the night (0-10)")
    sleep_quality: SleepQuality = Field(..., description="Self-reported sleep quality rating")
    mood_on_wake: MoodOnWake = Field(..., description="Self-reported mood upon waking")
    caffeine_after_2pm: bool = Field(..., description="Whether caffeine was consumed after 2:00 PM")
    exercise_today: bool = Field(..., description="Whether the user exercised during the day")
    screen_time_before_bed: bool = Field(..., description="Whether the user had screen time within 1 hour before bed")
    focus_level: int = Field(..., ge=1, le=5, description="Self-reported focus/concentration level today (1=very poor, 5=excellent)")
    energy_level: int = Field(..., ge=1, le=5, description="Self-reported energy level today (1=very low, 5=excellent)")
    notes: Optional[str] = Field(None, description="Optional text notes provided by the user")
    score: Optional[int] = Field(None, ge=0, le=100, description="Overall sleep score (0-100), calculated by Analyzer Agent")

    @property
    def date(self) -> date:
        """
        Convenience accessor: 'date' is only an input/output alias for
        entry_date (pydantic field aliases don't create a real attribute),
        but several call sites (mcp_server.py, tracker.py, reporter.py)
        access entry.date directly. This property makes that work without
        renaming the underlying field or touching those call sites.
        """
        return self.entry_date


class UserProfileSchema(BaseModel):
    """
    Represents user preferences, goals, and tracking statistics.

    Used by:
    - Profile Agent: To manage, retrieve, and update user settings and check-in metrics.
    - Intake/Analyzer/Circadian Agents: To retrieve user goals (e.g., target wake time)
      and caffeine sensitivity to contextualize feedback.

    MCP Tool connections:
    - UserProfileMCP: Connects to `get_user_profile` (to read profile data) and
      `update_profile_stats` (to update check-in streak and total entry counts).
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    username: str = Field(..., description="Username of the user")
    target_wake_time: str = Field(..., description="Desired wake time in HH:MM format")
    target_bedtime: str = Field(default="23:00", description="Current plan's target bedtime in HH:MM format, adjusted over time based on progress")
    target_sleep_duration: float = Field(default=8.0, description="Target sleep duration in hours")
    caffeine_sensitivity: CaffeineSensitivity = Field(default=CaffeineSensitivity.MEDIUM, description="User sensitivity level to caffeine")
    check_in_streak: int = Field(default=0, ge=0, description="Current consecutive day check-in streak")
    total_entries: int = Field(default=0, ge=0, description="Total number of logged sleep entries")
    plan_status: PlanStatus = Field(default=PlanStatus.INSUFFICIENT_DATA, description="Current direction of the user's sleep trend relative to their plan")
    plan_updated_at: Optional[datetime] = Field(None, description="Timestamp when the plan target was last adjusted")
    telegram_chat_id: Optional[str] = Field(None, description="Linked Telegram chat ID for delivering check-in prompts and reports as notifications. None if not yet linked.")
    telegram_linked_at: Optional[datetime] = Field(None, description="Timestamp when the Telegram account was linked, if applicable")
    preferred_checkin_time: Optional[str] = Field(None, description="Preferred daily check-in notification time in HH:MM (24-hour) format. None means no notification scheduled yet.")
    created_at: datetime = Field(..., description="Timestamp when the user profile was created")


class CircadianSchema(BaseModel):
    """
    Represents personalized circadian rhythm sleep/wake schedule recommendations.

    Used by:
    - Circadian Agent: To generate daily recommended schedules and wind-down timings.

    MCP Tool connections:
    - CircadianCalculatorMCP: Connects to `calculate_circadian_schedule` to compute
      optimal bedtimes and wind-down periods based on target wake times and cycles.
    """
    recommended_bedtime: str = Field(..., description="Optimal bedtime recommended in HH:MM format")
    recommended_wake_time: str = Field(..., description="Optimal wake time recommended in HH:MM format")
    sleep_window_hours: float = Field(..., description="Total duration of the recommended sleep window in hours")
    wind_down_start: str = Field(..., description="Recommended start time for wind-down routine in HH:MM format (15 min before bedtime)")
    notes: str = Field(..., description="Personalized guidelines or notes explaining the recommendation")


class SmartFollowUpSchema(BaseModel):
    """
    Represents personalized follow-up questions triggered by sleep patterns or anomalies.

    Used by:
    - Follow-up Agent: To compile targeted questions for the user's next check-in.

    MCP Tool connections:
    - FollowUpGeneratorMCP: Connects to `generate_smart_followup` to evaluate the latest
      sleep logs and select relevant follow-up questions and their reasons.
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    entry_date: date = Field(alias="date", description="Date for which these follow-up questions are generated")
    core_questions: list[str] = Field(..., max_items=3, description="Always asked standard questions (maximum of 3)")
    followup_questions: list[str] = Field(..., max_items=3, description="Conditional follow-up questions based on sleep patterns (maximum of 3)")
    triggered_by: list[str] = Field(..., description="List of detected patterns/reasons that triggered the follow-up questions")


class PlanAdjustmentSchema(BaseModel):
    """
    Represents the outcome of evaluating a user's adaptive sleep plan: whether
    their trend is improving or declining, and what (if anything) changed.

    Used by:
    - Scheduler Agent: To decide whether to shift the user's target bedtime/wake
      time based on recent performance, and to hand off the decision to the
      Reporter Agent for messaging.

    MCP Tool connections:
    - PlanEngineMCP: Connects to `evaluate_plan` to compute the rolling trend,
      weekly comparison, and streak-override checks, and to persist any change
      to the user's stored plan target.
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    status: PlanStatus = Field(..., description="Direction of the user's sleep trend relative to the current plan")
    triggered_by: PlanTrigger = Field(..., description="Which evaluation rule caused this decision (rolling trend, weekly comparison, streak override, or none)")
    adjusted: bool = Field(..., description="Whether the stored plan target was actually changed as a result of this evaluation")
    previous_target_bedtime: Optional[str] = Field(None, description="The target bedtime in effect before this evaluation, in HH:MM format")
    new_target_bedtime: Optional[str] = Field(None, description="The target bedtime in effect after this evaluation, in HH:MM format (same as previous if not adjusted)")
    rolling_avg_score: Optional[float] = Field(None, description="7-day rolling average sleep score used in the evaluation")
    previous_week_avg_score: Optional[float] = Field(None, description="Average sleep score from the prior 7-day window, for weekly comparison")
    reason: str = Field(..., description="Human-readable explanation of the decision, suitable for inclusion in user-facing messages")


class TelegramLinkSchema(BaseModel):
    """
    Represents the outcome of linking a web-registered user's account to a
    Telegram chat, so daily check-in prompts and weekly reports can be
    delivered as Telegram notifications instead of requiring the user to
    visit the web dashboard to be reminded.

    Used by:
    - Bot transport (bot.py): When a user starts the bot via a deep link
      carrying their web user_id as the /start payload, this records the
      mapping from that user_id to the Telegram chat_id that sent /start.

    MCP Tool connections:
    - UserProfileMCP: Connects to `link_telegram` to persist the chat_id
      against the existing user_id row (created during web registration).
    """
    user_id: str = Field(..., description="The web-registered user_id being linked")
    telegram_chat_id: str = Field(..., description="The Telegram chat ID that issued the /start <user_id> deep link")
    already_linked: bool = Field(..., description="True if this user_id was already linked to a Telegram chat (re-linking overwrites the previous chat_id)")
    linked_at: datetime = Field(..., description="Timestamp when this link was recorded")


class SleepAnalysisSchema(BaseModel):
    """
    Represents a statistical and qualitative summary of sleep logs over a given period.

    Used by:
    - Analyzer Agent: To aggregate metrics, identify correlations, and generate recommendations.
    - Report Agent: To embed inside weekly summaries and report cards.

    MCP Tool connections:
    - SleepAnalyzerMCP: Connects to `analyze_sleep_period` to perform aggregations and
      run correlation analysis on sleep impact factors.
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    period_days: int = Field(..., description="The time window of analysis in days")
    average_score: float = Field(..., description="Average sleep score over the period")
    average_duration: float = Field(..., description="Average sleep duration in hours over the period")
    average_wake_ups: float = Field(..., description="Average nightly wake-up count over the period")
    best_night: Optional[SleepEntrySchema] = Field(None, description="The SleepEntrySchema of the night with the highest score")
    worst_night: Optional[SleepEntrySchema] = Field(None, description="The SleepEntrySchema of the night with the lowest score")
    patterns_detected: list[str] = Field(..., description="List of lifestyle or quality patterns detected")
    recommendations: list[str] = Field(..., description="Coaching recommendations and action items")
    verdict: VerdictLabel = Field(..., description="Overall health classification label")
    streak_days: int = Field(..., description="Number of consecutive check-ins during this analysis period")
    caffeine_impact: Optional[str] = Field(None, description="Analyzed correlation summary of late caffeine consumption on sleep")
    exercise_impact: Optional[str] = Field(None, description="Analyzed correlation summary of daily exercise on sleep")
    screen_time_impact: Optional[str] = Field(None, description="Analyzed correlation summary of pre-bed screen time on sleep")


class WeeklyReportSchema(BaseModel):
    """
    Represents a comprehensive weekly sleep report delivered to the user.

    Used by:
    - Report Agent: To package the analysis, visualization charts, and goals for the user.

    MCP Tool connections:
    - WeeklyReportGeneratorMCP: Connects to `generate_weekly_report` to persist the report,
      and `generate_sleep_chart` to render and output the path to the Plotly chart image.
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    week_start: date = Field(..., description="Start date of the weekly reporting period")
    week_end: date = Field(..., description="End date of the weekly reporting period")
    analysis: SleepAnalysisSchema = Field(..., description="Detailed sleep analysis for the week")
    plotly_chart_path: Optional[str] = Field(None, description="Local filesystem or CDN path to the generated Plotly sleep chart image")
    milestone_message: Optional[str] = Field(None, description="Optional celebratory message if a milestone was reached")
    next_week_goal: str = Field(..., description="Personalized actionable target for the next week")


class MCPToolResponseSchema(BaseModel):
    """
    Represents a standardized response wrapper for any MCP tool executed by the system.

    Used by:
    - Coordinator/Orchestrator Agent: To process, validate, and handle execution outputs
      from various external tools and route to the next agent if necessary.

    MCP Tool connections:
    - Universal wrapper: Connects to any and all registered MCP tools to format execution feedback.
    """
    tool_name: str = Field(..., description="The name of the MCP tool that was executed")
    success: bool = Field(..., description="Indicates whether the tool executed successfully without uncaught errors")
    data: Optional[dict] = Field(None, description="Successful payload or output dictionary returned by the tool")
    error: Optional[str] = Field(None, description="Error message details if success is False")
    agent_next: Optional[str] = Field(None, description="Determines which agent should receive control next based on output")


class A2AMessageSchema(BaseModel):
    """
    Represents a standard message schema for Agent-to-Agent (A2A) communications.

    Used by:
    - Coordinator Agent and all operational agents: To exchange context, trigger events,
      and orchestrate steps in the Sleep Concierge system.

    MCP Tool connections:
    - A2AMessageBusMCP: Connects to `route_a2a_message` to dispatch messages to the
      target agent's inbox, and `retrieve_session_queue` to pull pending messages.
    """
    from_agent: str = Field(..., description="Name of the agent sending the message")
    to_agent: str = Field(..., description="Name of the agent intended to receive the message")
    message_type: str = Field(..., description="The type of message (e.g. INTAKE_COMPLETE, ANALYSIS_REQUEST)")
    payload: dict = Field(..., description="The data payload passed between the agents")
    timestamp: datetime = Field(..., description="Timestamp when the message was dispatched")
    session_id: str = Field(..., description="Unique session identifier for tracing conversation/workflow flows")


class ChatMessage(BaseModel):
    """A single message in a concierge check-in conversation."""
    role: Literal["user", "assistant"] = Field(..., description="Who sent the message")
    content: str = Field(..., description="Message text")


class PartialSleepSlots(BaseModel):
    """Incrementally collected sleep fields during a concierge check-in."""
    bedtime: Optional[str] = None
    wake_time: Optional[str] = None
    wake_up_count: Optional[int] = Field(None, ge=0, le=10)
    sleep_quality: Optional[SleepQuality] = None
    mood_on_wake: Optional[MoodOnWake] = None
    caffeine_after_2pm: Optional[bool] = None
    exercise_today: Optional[bool] = None
    screen_time_before_bed: Optional[bool] = None
    focus_level: Optional[int] = Field(None, ge=1, le=5)
    energy_level: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = None


REQUIRED_CHECKIN_SLOTS = (
    "bedtime",
    "wake_time",
    "wake_up_count",
    "sleep_quality",
    "mood_on_wake",
    "caffeine_after_2pm",
    "exercise_today",
    "screen_time_before_bed",
)


class CheckinSessionState(BaseModel):
    """Stateful concierge check-in session tracked across multiple turns."""
    user_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    slots: PartialSleepSlots = Field(default_factory=PartialSleepSlots)
    slot_confidence: dict[str, SlotConfidence] = Field(default_factory=dict)
    session_context: Optional[str] = Field(
        None, description="Optional context from prior sleep logs or scheduler hints"
    )
    curiosity_notes: list[str] = Field(default_factory=list)

    def missing_slots(self) -> list[str]:
        missing = []
        for name in REQUIRED_CHECKIN_SLOTS:
            conf = self.slot_confidence.get(name, SlotConfidence.UNKNOWN)
            if conf == SlotConfidence.UNKNOWN:
                missing.append(name)
        return missing

    def is_complete(self) -> bool:
        return len(self.missing_slots()) == 0


class ConciergeTurnResponse(BaseModel):
    """Structured output from one concierge turn."""
    acknowledgment: str = Field(..., description="Brief empathetic reflection on what the user said")
    updated_slots: PartialSleepSlots = Field(default_factory=PartialSleepSlots)
    slot_confidence: dict[str, SlotConfidence] = Field(default_factory=dict)
    follow_up: Optional[str] = Field(None, description="Single contextual question, or null when complete")
    is_complete: bool = False
    curiosity_note: Optional[str] = Field(None, description="Optional context to save in notes")