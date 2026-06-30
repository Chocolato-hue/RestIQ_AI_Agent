"""Wrap service results in MCPToolResponseSchema dicts for the MCP server."""

from typing import Any, Optional

from schemas import MCPToolResponseSchema


def success(
    tool_name: str,
    data: Any,
    agent_next: Optional[str] = None,
) -> dict:
    return MCPToolResponseSchema(
        tool_name=tool_name,
        success=True,
        data=data,
        error=None,
        agent_next=agent_next,
    ).model_dump(mode="json")


def failure(tool_name: str, error: Exception | str) -> dict:
    message = str(error)
    return MCPToolResponseSchema(
        tool_name=tool_name,
        success=False,
        data=None,
        error=message,
        agent_next=None,
    ).model_dump(mode="json")
