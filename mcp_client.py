"""
mcp_client.py — RestIQ MCP Client
Helper module to call MCP tools from mcp_server.py.
"""

import asyncio
import json
import sys
import os
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def get(tool_name: str, arguments: dict) -> dict:
    """
    Synchronously calls an MCP tool by spawning mcp_server.py as a subprocess.
    """
    async def _run():
        project_root = os.path.dirname(os.path.abspath(__file__))
        server_path = os.path.join(project_root, "mcp_server.py")
        
        # Launch server with correct Python executable and pass environment variables (API keys, etc.)
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path],
            env=os.environ.copy()
        )
        
        async with AsyncExitStack() as stack:
            transport = await stack.enter_async_context(stdio_client(server_params))
            read, write = transport
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            result = await session.call_tool(tool_name, arguments=arguments)
            if result.content:
                text_content = result.content[0].text
                return json.loads(text_content)
            raise ValueError(f"Tool {tool_name} returned no content.")
            
    return asyncio.run(_run())
