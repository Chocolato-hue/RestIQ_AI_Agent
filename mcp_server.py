"""
mcp_server.py — Thin MCP transport layer for RestIQ

Tool implementations live in tools/; database setup in db/.
This file only registers tools as MCP endpoints for external clients
(Google ADK Web UI, etc.).

The main app (agents, Streamlit, Telegram bot) calls tools/ directly.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("mcp_server")

import db  # noqa: E402, F401 — ensures DB init

from tools import (  # noqa: E402
    analyzer,
    circadian,
    intake,
    mcp_adapter,
    plan,
    profile,
    reporting,
    storage,
)

mcp = FastMCP("restiq-sleep-server")


@mcp.tool()
def register_user(user_id: str, username: str, target_wake_time: str = "07:00") -> dict:
    """Create a web user profile (idempotent)."""
    try:
        result = profile.register_user(user_id, username, target_wake_time)
        return mcp_adapter.success("register_user", result.model_dump(mode="json"))
    except Exception as e:
        logger.error("[MCP] register_user: %s", e, exc_info=True)
        return mcp_adapter.failure("register_user", e)


@mcp.tool()
def link_telegram(user_id: str, telegram_chat_id: str) -> dict:
    """Link a web user_id to a Telegram chat for notifications."""
    try:
        result = profile.link_telegram(user_id, telegram_chat_id)
        return mcp_adapter.success("link_telegram", result.model_dump(mode="json"))
    except Exception as e:
        logger.error("[MCP] link_telegram: %s", e, exc_info=True)
        return mcp_adapter.failure("link_telegram", e)


@mcp.tool()
def parse_sleep_input(user_id: str, raw_text: str) -> dict:
    """Parse natural language sleep check-in into structured data."""
    try:
        entry = intake.parse_sleep_input(user_id, raw_text)
        return mcp_adapter.success(
            "parse_sleep_input",
            entry.model_dump(mode="json"),
            agent_next="TrackerAgent",
        )
    except Exception as e:
        logger.error("[MCP] parse_sleep_input: %s", e, exc_info=True)
        return mcp_adapter.failure("parse_sleep_input", e)


@mcp.tool()
def calculate_circadian(wake_time: str, sleep_duration: float = 8.0) -> dict:
    """Calculate recommended bedtime and wind-down schedule."""
    try:
        result = circadian.calculate_circadian(wake_time, sleep_duration)
        return mcp_adapter.success("calculate_circadian", result.model_dump(mode="json"))
    except Exception as e:
        logger.error("[MCP] calculate_circadian: %s", e, exc_info=True)
        return mcp_adapter.failure("calculate_circadian", e)


@mcp.tool()
def store_sleep_data(entry: dict) -> dict:
    """Save a sleep entry and update the user's streak."""
    try:
        storage.store_sleep_data(entry)
        user_id = entry.get("user_id", "unknown")
        return mcp_adapter.success(
            "store_sleep_data",
            {"message": "Sleep entry successfully recorded", "user_id": user_id},
            agent_next="AnalyzerAgent",
        )
    except Exception as e:
        logger.error("[MCP] store_sleep_data: %s", e, exc_info=True)
        return mcp_adapter.failure("store_sleep_data", e)


@mcp.tool()
def evaluate_plan(user_id: str, commit_weekly_adjustment: bool = False) -> dict:
    """Evaluate and optionally adjust the user's adaptive sleep plan."""
    try:
        result = plan.evaluate_plan(user_id, commit_weekly_adjustment)
        return mcp_adapter.success(
            "evaluate_plan",
            result.model_dump(mode="json"),
            agent_next="ReporterAgent",
        )
    except Exception as e:
        logger.error("[MCP] evaluate_plan: %s", e, exc_info=True)
        return mcp_adapter.failure("evaluate_plan", e)


@mcp.tool()
def analyze_patterns(user_id: str, days: int = 7) -> dict:
    """Analyze sleep patterns over the last N days."""
    try:
        analysis, entries = analyzer.analyze_patterns(user_id, days)
        return mcp_adapter.success(
            "analyze_patterns",
            {
                "analysis": analysis.model_dump(mode="json"),
                "entries": [e.model_dump(mode="json") for e in entries],
            },
            agent_next="ReporterAgent",
        )
    except Exception as e:
        logger.error("[MCP] analyze_patterns: %s", e, exc_info=True)
        return mcp_adapter.failure("analyze_patterns", e)


@mcp.tool()
def generate_report(user_id: str) -> dict:
    """Generate a weekly sleep report with chart."""
    try:
        report = reporting.generate_report(user_id)
        return mcp_adapter.success("generate_report", report.model_dump(mode="json"))
    except Exception as e:
        logger.error("[MCP] generate_report: %s", e, exc_info=True)
        return mcp_adapter.failure("generate_report", e)


if __name__ == "__main__":
    mcp.run()
