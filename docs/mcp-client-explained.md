# What Was Wrong & How We Fixed It (Beginner-Friendly)

## The setup in one sentence

RestIQ has **tools** (save sleep data, analyze patterns, etc.) living in `mcp_server.py`. Other parts of the app (agents, Streamlit, Telegram bot) call those tools through a small helper: **`mcp_client.py`**.

Think of `mcp_server.py` as the **kitchen**, and `mcp_client.py` as the **waiter** that brings orders to the kitchen.

---

## What was wrong

The old waiter did something very inefficient:

> **Every single order = open a brand-new kitchen, cook one dish, then shut the kitchen down.**

In code terms, **every tool call** did this:

1. Start a new Python process running `mcp_server.py`
2. Say hello to it (MCP “initialize session”)
3. Ask for one thing (e.g. “calculate bedtime”)
4. Kill the process
5. Repeat for the next tool

A daily check-in isn’t one tool — it’s several in a row:

```
parse sleep text  →  save to database  →  calculate bedtime  →  evaluate plan  →  analyze patterns
```

So **one check-in ≈ 5 new kitchens opened and closed**. That’s slow, wasteful, and easy to break (each startup has overhead, DB init, etc.).

### Simple analogy

Imagine calling a restaurant **5 times**, and each time they:

- Hire new staff
- Unlock the building
- Cook your one item
- Lock up and go home

You’d only need **one kitchen open** and place **5 orders** while it stays open. That’s what we wanted.

---

## Why it was built that way (not “stupid,” just demo-style)

This pattern is common when learning **MCP (Model Context Protocol)**:

- MCP is designed for **separate programs** talking over stdin/stdout (like a plugin system).
- Spawning a subprocess per call is the **simplest** way to wire that up.
- It works, but it’s **not** how you’d run it in production when everything already lives in the **same project on the same machine**.

So: good for learning MCP, bad for performance when your own Python code is calling your own Python server over and over.

---

## How we fixed it

We gave `mcp_client.py` **two ways** to call tools, instead of always spawning a new process.

### Fix 1: In-process (default) — “walk into the kitchen yourself”

**Default mode:** `RESTIQ_MCP_TRANSPORT=inprocess` (or just leave it unset)

Instead of starting a subprocess, the client **imports `mcp_server.py` directly** and calls the same functions the MCP tools wrap.

```
Before:  agent → subprocess → mcp_server function
After:   agent → mcp_server function   (same process, no subprocess)
```

The `@mcp.tool()` decorator registers the function for **external** MCP clients (like Google ADK). The function itself is still a normal Python function you can call directly.

**Analogy:** You’re already inside the restaurant — you walk to the kitchen and ask for what you need. No new building, no new staff.

### Fix 2: Persistent stdio (optional) — “one kitchen, many orders”

**Optional mode:** `RESTIQ_MCP_TRANSPORT=stdio`

If you still want the **real MCP wire protocol** (for testing or demos), we start **one** `mcp_server.py` subprocess and **keep it alive**. All tool calls reuse that same connection.

```
Before:  spawn → call → kill → spawn → call → kill → ...
After:   spawn once → call → call → call → ... → close on exit
```

**Analogy:** The kitchen opens once in the morning; you place five orders through the same window; it closes when the app shuts down.

---

## What didn’t change

- **`mcp_server.py`** — same tools, same logic, same database.
- **Google ADK agent** (`restiq_agent/agent.py`) — still uses its **own** MCP connection for the ADK Web UI. We didn’t touch that.
- **Agent code** (`agents/intake.py`, etc.) — still call `mcp_client.get("tool_name", {...})`. Same API, faster underneath.

---

## Before vs after (check-in)

| | Before | After (default) |
|---|--------|------------------|
| Subprocesses per check-in | ~5 | **0** |
| Speed | Slow (startup every time) | Much faster |
| Complexity for callers | Same | Same |

Rough benchmark from our test: **3 tool calls** went from “multiple process startups” to **~23ms total** in-process.

---

## Mental model to keep

```
┌─────────────────────────────────────────────────────────┐
│  Your app (Streamlit, bot, pipeline, agents)            │
│                                                         │
│   mcp_client.get("calculate_circadian", {...})          │
│              │                                          │
│              ▼                                          │
│   ┌──────────────────────┐                              │
│   │  inprocess (default) │  → call function directly    │
│   │  stdio (optional)    │  → one long-lived subprocess │
│   └──────────────────────┘                              │
│              │                                          │
│              ▼                                          │
│         mcp_server.py (the actual tool logic)           │
└─────────────────────────────────────────────────────────┘
```

**Wrong:** treat every tool call like a new remote service.

**Fixed:** same machine, same codebase → call the functions directly (or keep one connection open if you need real MCP).

---

## One-line summary

**Before:** every tool call booted a mini server and shut it down.

**After:** we either call the server code directly (default) or keep one server running for all calls (optional stdio mode).
