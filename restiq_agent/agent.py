"""
restiq_agent/agent.py — ADK root agent for RestIQ

This is the entry point `adk web` looks for: it scans the directory passed
to `adk web` for subfolders containing an `agent.py` (or `root_agent.yaml`)
that defines a module-level `root_agent`.

Two tool surfaces are exposed, deliberately:

1. The raw MCP tools from mcp_server.py, via McpToolset connecting over
   stdio — thin wrappers around tools/ for the ADK Web UI tool inspector.

2. Thin wrapper functions around pipeline.py's deterministic orchestrator
   (run_checkin, run_weekly_report). These exist because the multi-step
   ordering inside handle_checkin/handle_weekly_report (intake -> store ->
   circadian -> plan evaluation -> analysis, with specific commit/no-commit
   gating) is business logic that should stay deterministic, not be
   re-derived by the LLM calling raw MCP tools in whatever order it guesses.

The LLM decides WHEN to check in or pull a report; pipeline.py still decides
HOW that flow executes internally.
"""

import sys
import os

# Make the RestIQ project root importable (this file lives in
# restiq/restiq_agent/, so the project root is one level up).
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

from pipeline import run_checkin as _run_checkin
from pipeline import run_weekly_report as _run_weekly_report

# ──────────────────────────────────────────────────────────────────────────────
# Tool surface 1: raw MCP tools (thin wrappers over tools/)
# ──────────────────────────────────────────────────────────────────────────────

restiq_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[os.path.join(PROJECT_ROOT, "mcp_server.py")],
            env=os.environ.copy(),
        ),
        timeout=30,
    ),
)

# ──────────────────────────────────────────────────────────────────────────────
# Tool surface 2: deterministic pipeline orchestrator, wrapped as plain
# functions. ADK accepts plain callables directly in `tools=[...]`.
# ──────────────────────────────────────────────────────────────────────────────

def checkin(user_id: str, raw_text: str) -> dict:
    """
    Runs the full RestIQ daily check-in pipeline for a user: parses their
    natural-language sleep description, stores it, calculates tonight's
    recommended bedtime, evaluates their adaptive plan (without committing
    a weekly adjustment), and runs a 7-day pattern analysis.

    Args:
        user_id: Unique identifier for the user (any stable string works,
            e.g. a Telegram chat ID or a test name).
        raw_text: The user's free-text description of last night's sleep,
            e.g. "went to bed at 11, woke at 7, woke up twice, felt okay,
            no caffeine, exercised, used my phone before bed".

    Returns:
        A dict with: reply_message (str summary), entry (sleep log details),
        circadian (tonight's recommended schedule), plan_adjustment (whether
        the adaptive plan changed), and analysis (7-day pattern summary).
    """
    result = _run_checkin(user_id, raw_text)
    return {
        "reply_message": result["reply_message"],
        "entry": result["entry"].model_dump(mode="json"),
        "circadian": result["circadian"].model_dump(mode="json"),
        "plan_adjustment": result["plan_adjustment"].model_dump(mode="json"),
        "analysis": result["analysis"].model_dump(mode="json"),
    }


def weekly_report(user_id: str) -> dict:
    """
    Generates the full RestIQ weekly report for a user: aggregates the last
    7 days of sleep data, evaluates the adaptive plan (committing a target
    bedtime adjustment if a clear trend is confirmed), and produces a
    formatted summary message plus a chart path.

    Args:
        user_id: Unique identifier for the user.

    Returns:
        A dict with: telegram_message (formatted summary text),
        plan_adjustment (whether/why the plan changed this week),
        chart_path (filesystem path to the generated sleep chart image).
    """
    result = _run_weekly_report(user_id)
    return {
        "telegram_message": result["telegram_message"],
        "plan_adjustment": result["plan_adjustment"].model_dump(mode="json"),
        "chart_path": result["chart_path"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Root agent
# ──────────────────────────────────────────────────────────────────────────────

root_agent = Agent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="restiq_agent",
    description="RestIQ sleep concierge — logs check-ins, tracks patterns, and adapts a sleep plan over time.",
    instruction=(
        "You are RestIQ, a warm and curious sleep concierge — not a survey bot.\n\n"
        "Conversation style:\n"
        "- Acknowledge what the user shares before asking anything new.\n"
        "- Ask at most ONE follow-up at a time when information is missing.\n"
        "- Never re-ask about things they already denied (e.g. no caffeine → don't ask caffeine timing).\n"
        "- Follow threads they open (forced wake, stress, screens) with genuine curiosity.\n"
        "- Before calling `checkin`, briefly summarize what you understood and ask "
        "'Does that sound right?' unless they already gave a complete, clear picture.\n\n"
        "Tools:\n"
        "1. `checkin` and `weekly_report` run RestIQ's full pipeline end-to-end "
        "in the correct order. Prefer these for normal conversation: once you have "
        "enough detail about how they slept, call `checkin` with a transcript of "
        "the conversation. If they ask for a report, progress, or trends, call "
        "`weekly_report`.\n\n"
        "2. The individual MCP tools (parse_sleep_input, store_sleep_data, "
        "calculate_circadian, analyze_patterns, generate_report, evaluate_plan) "
        "are lower-level building blocks. Only call these directly if the user "
        "explicitly asks to inspect or test one specific step in isolation — "
        "for normal check-ins, use `checkin`/`weekly_report` instead so the "
        "steps run in the right order with the right gating.\n\n"
        "Always ask the user for their user_id if it hasn't been established "
        "in the conversation yet; don't invent one."
    ),
    tools=[checkin, weekly_report, restiq_mcp_toolset],
)