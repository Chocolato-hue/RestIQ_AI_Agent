"""
agent_server.py — FastAPI server for RestIQ

Two responsibilities:
1. AG-UI / CopilotKit bridge: wraps the ADK root_agent via ag-ui-adk so a
   CopilotKit frontend can talk to it over HTTP at /api/copilotkit.
2. Dashboard REST endpoints for the Next.js / Streamlit frontend:
   history, profile, report, plan status, and user registration.
"""

import sys
import os

# Ensure project root is importable (same trick used in restiq_agent/agent.py)
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── AG-UI ↔ ADK adapter ─────────────────────────────────────────────────────
from ag_ui_adk import ADKAgent, add_adk_fastapi_endpoint

# ── DB init (creates tables on first import) ─────────────────────────────────
import db  # noqa: F401  — side-effect: calls init_db()

# ── RestIQ internals ─────────────────────────────────────────────────────────
from restiq_agent.agent import root_agent
from pipeline import run_checkin, run_weekly_report
from agents.tracker import run_get_history, run_get_latest
from agents.scheduler import run_evaluate_plan
from agents.analyzer import run_analyze
from agents.reporter import run_generate
from tools import profile as profile_tool
from schemas import (
    SleepEntrySchema,
    UserProfileSchema,
    WeeklyReportSchema,
    PlanAdjustmentSchema,
    SleepAnalysisSchema,
)

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("agent_server")

# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI app
# ═══════════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="RestIQ Agent Server",
    version="0.1.0",
    description="AG-UI bridge + dashboard REST API for RestIQ sleep concierge",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── AG-UI endpoint (wraps the ADK root_agent for CopilotKit frontends) ──────
adk_agent = ADKAgent(
    adk_agent=root_agent,
    app_name="restiq",
)

add_adk_fastapi_endpoint(app, adk_agent, "/api/copilotkit")


# ═══════════════════════════════════════════════════════════════════════════════
# Request / response models for the REST endpoints
# ═══════════════════════════════════════════════════════════════════════════════


class RegisterRequest(BaseModel):
    user_id: str
    username: str
    target_wake_time: str = "07:00"
    age_years: Optional[float] = None


class CheckinRequest(BaseModel):
    user_id: str
    raw_text: str


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard REST endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/api/history/{user_id}")
async def get_history(user_id: str, days: int = Query(default=7, ge=1, le=90)):
    """Fetch sleep entries for the last N days."""
    try:
        entries = run_get_history(user_id, days=days)
        return {
            "user_id": user_id,
            "days": days,
            "count": len(entries),
            "entries": [e.model_dump(mode="json") for e in entries],
        }
    except Exception as exc:
        logger.error("[API] get_history failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/profile/{user_id}")
async def get_profile(user_id: str):
    """Return the full user profile."""
    try:
        profile: UserProfileSchema = profile_tool.get_user_profile(user_id)
        return profile.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("[API] get_profile failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/report/{user_id}")
async def get_report(user_id: str):
    """Generate and return weekly report data."""
    try:
        result = run_weekly_report(user_id)
        return {
            "telegram_message": result["telegram_message"],
            "plan_adjustment": result["plan_adjustment"].model_dump(mode="json"),
            "chart_path": result["chart_path"],
        }
    except Exception as exc:
        logger.error("[API] get_report failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/plan/{user_id}")
async def get_plan(user_id: str):
    """Evaluate the user's adaptive plan status (read-only, no commit)."""
    try:
        adjustment: PlanAdjustmentSchema = run_evaluate_plan(
            user_id, commit_weekly_adjustment=False
        )
        return adjustment.model_dump(mode="json")
    except Exception as exc:
        logger.error("[API] get_plan failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/register")
async def register_user(req: RegisterRequest):
    """Register a new user profile."""
    try:
        profile: UserProfileSchema = profile_tool.register_user(
            user_id=req.user_id,
            username=req.username,
            target_wake_time=req.target_wake_time,
            age_years=req.age_years,
        )
        return profile.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("[API] register_user failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/checkin")
async def do_checkin(req: CheckinRequest):
    """Run the full check-in pipeline and return results."""
    try:
        result = run_checkin(req.user_id, req.raw_text)
        return {
            "reply_message": result["reply_message"],
            "entry": result["entry"].model_dump(mode="json"),
            "circadian": result["circadian"].model_dump(mode="json"),
            "plan_adjustment": result["plan_adjustment"].model_dump(mode="json"),
            "analysis": result["analysis"].model_dump(mode="json"),
        }
    except Exception as exc:
        logger.error("[API] do_checkin failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/latest/{user_id}")
async def get_latest(user_id: str):
    """Return the most recent sleep entry for the user."""
    try:
        entry = run_get_latest(user_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="No sleep entries found")
        return entry.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[API] get_latest failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/analysis/{user_id}")
async def get_analysis(user_id: str, days: int = Query(default=7, ge=1, le=90)):
    """Run the analyzer over the last N days and return the analysis."""
    try:
        analysis: SleepAnalysisSchema = run_analyze(user_id, days=days)
        return analysis.model_dump(mode="json")
    except Exception as exc:
        logger.error("[API] get_analysis failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# Health check
# ═══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════════════════
# Dev entrypoint
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
