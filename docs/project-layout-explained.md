# RestIQ Project Layout: db / tools / agents (Beginner-Friendly)

## The setup in one sentence

RestIQ is organized into **three layers**: **`db/`** stores data, **`tools/`** implements sleep actions, and **`agents/`** orchestrates those tools into user-facing flows. **`mcp_server.py`** is only an external front door for Google ADK.

---

## Why three folders?

A multi-agent app naturally has three different jobs:

| Layer | Job | Analogy |
|-------|-----|---------|
| **`db/`** | Database setup and data access | The **pantry & ledger** — where records live |
| **`tools/`** | Single-purpose actions (parse text, save entry, analyze week) | The **recipes** — one dish each |
| **`agents/`** | Coordinate tools in a conversation flow | The **chefs** — decide which recipe when |

Before, all of this was mixed in one big `mcp_server.py` (and briefly a `services/` folder). That made it hard to see what was *data*, what was *logic*, and what was *orchestration*.

---

## Folder layout

```text
RestIQ/
├── db/                    # Data layer
│   ├── sqlite.py          # Schema, migrations, DB_FILE
│   └── entries.py         # Load/save sleep rows from SQLite
│
├── tools/                 # Tool implementations (plain Python)
│   ├── scoring.py         # Sleep score + duration math
│   ├── intake.py          # Gemini NL → structured log
│   ├── storage.py         # Persist entries + streaks
│   ├── circadian.py       # Bedtime recommendations
│   ├── plan.py            # Adaptive plan evaluation
│   ├── analyzer.py        # Pattern analysis
│   ├── reporting.py       # Weekly report + chart
│   ├── profile.py         # Register user, link Telegram
│   ├── analysis.py        # Shared analysis helpers
│   └── mcp_adapter.py     # JSON wrappers (MCP server only)
│
├── agents/                # Agent orchestration
│   ├── intake.py          # Calls tools/intake
│   ├── tracker.py         # Calls tools/storage, tools/analyzer
│   ├── scheduler.py       # Calls tools/circadian, tools/plan
│   ├── analyzer.py        # Calls tools/analyzer
│   └── reporter.py        # Calls tools/reporting
│
├── pipeline.py            # Multi-agent check-in / report flows
├── mcp_server.py          # Thin MCP wrapper → tools/ (ADK only)
├── streamlit_app.py       # Web UI
└── bot.py                 # Telegram UI
```

---

## How a check-in flows

```
User text (Streamlit / Telegram)
        │
        ▼
   pipeline.py          ← orchestrates the full flow
        │
        ├── agents/intake.py  →  tools/intake.py     (Gemini parse)
        ├── agents/tracker.py →  tools/storage.py   (save to db/)
        ├── agents/scheduler.py → tools/circadian.py, tools/plan.py
        └── agents/analyzer.py  → tools/analyzer.py  (reads via db/entries)
                                          │
                                          ▼
                                    db/sqlite.py (SQLite file)
```

**Agents never touch MCP.** They call **`tools/`** directly. **`db/`** is only used by tools (and `bot.py` for scheduled broadcasts).

---

## What is MCP for?

**Only external clients** that speak the MCP protocol:

- Google ADK Web UI (`adk web restiq_agent`)
- Any future external agent connecting over stdio

`mcp_server.py` is ~150 lines: each `@mcp.tool()` calls the matching function in `tools/` and wraps the result as JSON.

```python
@mcp.tool()
def calculate_circadian(wake_time: str, sleep_duration: float = 8.0) -> dict:
    result = circadian.calculate_circadian(wake_time, sleep_duration)
    return mcp_adapter.success("calculate_circadian", result.model_dump(mode="json"))
```

The main app **does not** go through this path.

---

## Before vs after

| Before | After |
|--------|-------|
| Everything in `mcp_server.py` | Split into `db/`, `tools/`, `agents/` |
| `mcp_client.py` middleman | Removed — direct tool calls |
| MCP used internally | MCP only for ADK / outsiders |
| Hard to test one tool | Import `tools.intake` directly in a script |

---

## One-line summary

**`db/`** = where data lives · **`tools/`** = what each action does · **`agents/`** = how actions combine · **`mcp_server.py`** = optional external API for ADK demos.

See also: [mcp-client-explained.md](./mcp-client-explained.md) (earlier subprocess fix) and [services-architecture-explained.md](./services-architecture-explained.md) (intermediate refactor notes — `services/` was renamed to `tools/` + `db/`).
