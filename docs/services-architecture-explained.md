# RestIQ Architecture: Services vs MCP (Beginner-Friendly)

> **Note:** This doc describes an intermediate refactor. The current layout uses
> **`db/`**, **`tools/`**, and **`agents/`** instead of `services/`.
> See [project-layout-explained.md](./project-layout-explained.md) for the up-to-date structure.

## The setup in one sentence

RestIQ has **sleep tools** (save data, analyze patterns, generate reports). Those tools now live in **`services/`** as normal Python functions. **`mcp_server.py`** is only a thin wrapper so external tools (like Google ADK) can still talk to RestIQ over MCP.

---

## What was wrong before

Everything lived inside `mcp_server.py`, and the rest of the app called it through **`mcp_client.py`** — even though all the code runs on the **same machine in the same project**.

That meant:

1. **Confusing layers** — agents → mcp_client → mcp_server → actual logic (three hops for no reason)
2. **MCP everywhere** — MCP is meant for *external* programs talking to each other, not for your own Python files calling each other
3. **Slow** — originally each call even spawned a new subprocess (we fixed that earlier, but the fake “MCP sandwich” remained)

### Simple analogy

Imagine a restaurant where:

- The **kitchen** (`services/`) cooks the food
- A **waiter** (`mcp_client`) walks to a **phone booth** (`MCP protocol`) to order from the kitchen **in the same building**

You don't need the phone booth when you're already inside the restaurant. You walk to the kitchen and ask directly.

---

## How we fixed it (Option A)

We split the code into two clear layers:

```
services/          ← REAL logic (database, Gemini, scoring, reports)
mcp_server.py      ← THIN MCP wrapper (only for ADK / external clients)
agents/            ← call services/ directly (no mcp_client)
```

### Layer 1: `services/` — the kitchen

All business logic moved here:

| Module | What it does |
|--------|--------------|
| `services/db.py` | SQLite setup and migrations |
| `services/scoring.py` | Sleep score and duration math |
| `services/intake.py` | Parse natural language (Gemini) |
| `services/storage.py` | Save sleep entries, update streaks |
| `services/circadian.py` | Bedtime recommendations |
| `services/plan.py` | Adaptive plan evaluation |
| `services/analyzer.py` | Pattern analysis over N days |
| `services/reporting.py` | Weekly reports + charts |
| `services/profile.py` | User registration, Telegram linking |

These are **plain Python functions** that return typed objects (`SleepEntrySchema`, `WeeklyReportSchema`, etc.).

### Layer 2: `mcp_server.py` — the external menu

For **Google ADK Web UI** and any other MCP client, we kept a thin server that:

1. Receives MCP tool calls over stdio
2. Calls the matching `services/` function
3. Wraps the result in `MCPToolResponseSchema` JSON

Example:

```python
@mcp.tool()
def calculate_circadian(wake_time: str, sleep_duration: float = 8.0) -> dict:
    result = circadian.calculate_circadian(wake_time, sleep_duration)
    return mcp_adapter.success("calculate_circadian", result.model_dump(mode="json"))
```

No logic in the wrapper — just translate MCP ↔ Python.

### Layer 3: `agents/` — walk to the kitchen

Agents now import services directly:

```python
# Before
from mcp_client import get
response = get("parse_sleep_input", {"user_id": user_id, "raw_text": raw_text})

# After
from services import intake as intake_service
entry = intake_service.parse_sleep_input(user_id, raw_text)
```

Same for Streamlit, Telegram bot, and pipeline.

---

## What we removed

| Removed | Why |
|---------|-----|
| `mcp_client.py` | No longer needed — agents call `services/` directly |
| MCP from the main app path | MCP only used where it adds value (ADK) |

---

## Who uses what now

| Consumer | Calls | MCP? |
|----------|-------|------|
| Streamlit dashboard | `services.profile.register_user()` | No |
| Telegram bot | `services.profile.link_telegram()` | No |
| Pipeline + agents | `services.*` functions | No |
| Google ADK Web UI | `mcp_server.py` via stdio | **Yes** |
| `python mcp_server.py` | Standalone MCP server | **Yes** |

---

## Mental model

```
┌─────────────────────────────────────────────────────────────┐
│  Main app (Streamlit, bot, pipeline, agents)                │
│       │                                                     │
│       ▼  direct Python calls                                │
│  services/  ← all real logic lives here                     │
│       ▲                                                     │
│       │  thin wrapper only                                  │
│  mcp_server.py  ← only for ADK / external MCP clients       │
└─────────────────────────────────────────────────────────────┘
```

**Wrong:** every part of your own app pretending to be an external MCP client.

**Right:** internal code calls `services/` directly; MCP is only the **front door for outsiders**.

---

## One-line summary

**Before:** one big MCP server + a fake client layer, even for our own code.

**After:** logic in `services/`, app calls it directly, MCP kept only for ADK demos and external tools.

See also: [mcp-client-explained.md](./mcp-client-explained.md) for the earlier subprocess-per-call fix that led to this refactor.
