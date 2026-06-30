"""
mcp_client.py — RestIQ MCP Client

Calls tools registered in mcp_server.py without spawning a new subprocess
for every invocation.

Transport modes (RESTIQ_MCP_TRANSPORT env var):
  inprocess (default) — invoke the @mcp.tool functions directly in-process.
                        Fastest path for pipeline/agents/streamlit/bot.
  stdio               — one persistent MCP stdio session to mcp_server.py.
                        Use when validating the wire protocol; ADK uses its
                        own McpToolset connection separately.

Beginner-friendly explanation of the problem and fix:
  docs/mcp-client-explained.md
"""

from __future__ import annotations

import asyncio
import atexit
import importlib
import json
import logging
import os
import sys
import threading
from contextlib import AsyncExitStack
from typing import Any, Callable

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("mcp_client")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(PROJECT_ROOT, "mcp_server.py")
DEFAULT_TRANSPORT = "inprocess"
TOOL_CALL_TIMEOUT_SECONDS = 120

ToolFn = Callable[..., dict]


def _transport_mode() -> str:
    return os.environ.get("RESTIQ_MCP_TRANSPORT", DEFAULT_TRANSPORT).strip().lower()


# ──────────────────────────────────────────────────────────────────────────────
# In-process transport
# ──────────────────────────────────────────────────────────────────────────────

_tool_module = None
_tool_module_lock = threading.Lock()


def _load_tool_module():
    global _tool_module
    with _tool_module_lock:
        if _tool_module is None:
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            _tool_module = importlib.import_module("mcp_server")
        return _tool_module


def _get_tool_fn(tool_name: str) -> ToolFn:
    module = _load_tool_module()
    fn = getattr(module, tool_name, None)
    if fn is None or not callable(fn):
        raise ValueError(f"Unknown MCP tool: {tool_name}")
    return fn


def _call_inprocess(tool_name: str, arguments: dict) -> dict:
    fn = _get_tool_fn(tool_name)
    return fn(**arguments)


# ──────────────────────────────────────────────────────────────────────────────
# Persistent stdio transport (single subprocess, reused session)
# ──────────────────────────────────────────────────────────────────────────────

class _PersistentStdioClient:
    """Keeps one MCP stdio subprocess + ClientSession alive for reuse."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._loop_ready = threading.Event()
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop and self._thread and self._thread.is_alive():
            return self._loop

        self._loop_ready.clear()

        def _run_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._loop_ready.set()
            loop.run_forever()

        self._thread = threading.Thread(
            target=_run_loop,
            name="restiq-mcp-stdio",
            daemon=True,
        )
        self._thread.start()
        self._loop_ready.wait()
        assert self._loop is not None
        return self._loop

    async def _connect(self) -> None:
        await self._disconnect()

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[SERVER_PATH],
            env=os.environ.copy(),
        )

        stack = AsyncExitStack()
        transport = await stack.enter_async_context(stdio_client(server_params))
        read, write = transport
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        self._stack = stack
        self._session = session
        logger.debug("[MCP_CLIENT] Persistent stdio session connected")

    async def _disconnect(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None

    async def _call_async(self, tool_name: str, arguments: dict, *, retry: bool = True) -> dict:
        if self._session is None:
            await self._connect()

        assert self._session is not None
        try:
            result = await self._session.call_tool(tool_name, arguments=arguments)
        except Exception:
            if not retry:
                raise
            logger.warning(
                "[MCP_CLIENT] Stdio session failed for %s; reconnecting once",
                tool_name,
                exc_info=True,
            )
            await self._connect()
            result = await self._session.call_tool(tool_name, arguments=arguments)

        if not result.content:
            raise ValueError(f"Tool {tool_name} returned no content.")
        return json.loads(result.content[0].text)

    def call(self, tool_name: str, arguments: dict) -> dict:
        loop = self._ensure_loop()
        with self._lock:
            future = asyncio.run_coroutine_threadsafe(
                self._call_async(tool_name, arguments),
                loop,
            )
            return future.result(timeout=TOOL_CALL_TIMEOUT_SECONDS)

    def close(self) -> None:
        if self._loop is None:
            return

        async def _shutdown() -> None:
            await self._disconnect()

        with self._lock:
            try:
                future = asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
                future.result(timeout=10)
            except Exception:
                logger.debug("[MCP_CLIENT] Error during stdio shutdown", exc_info=True)
            finally:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread:
                    self._thread.join(timeout=5)
                self._loop = None
                self._thread = None


_stdio_client: _PersistentStdioClient | None = None
_stdio_client_lock = threading.Lock()


def _get_stdio_client() -> _PersistentStdioClient:
    global _stdio_client
    with _stdio_client_lock:
        if _stdio_client is None:
            _stdio_client = _PersistentStdioClient()
        return _stdio_client


def _call_stdio(tool_name: str, arguments: dict) -> dict:
    return _get_stdio_client().call(tool_name, arguments)


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def get(tool_name: str, arguments: dict) -> dict:
    """
    Call an MCP tool by name.

    Default transport is in-process (no subprocess). Set
    RESTIQ_MCP_TRANSPORT=stdio for a persistent stdio session instead.
    """
    mode = _transport_mode()
    if mode == "stdio":
        return _call_stdio(tool_name, arguments)
    if mode == "inprocess":
        return _call_inprocess(tool_name, arguments)
    raise ValueError(
        f"Unknown RESTIQ_MCP_TRANSPORT={mode!r}. Use 'inprocess' or 'stdio'."
    )


def close() -> None:
    """Shut down a persistent stdio session, if one was started."""
    global _stdio_client
    with _stdio_client_lock:
        if _stdio_client is not None:
            _stdio_client.close()
            _stdio_client = None


atexit.register(close)
