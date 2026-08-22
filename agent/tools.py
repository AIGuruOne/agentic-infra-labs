"""MCP client wiring: start the servers, discover their tools, translate.

Two translations happen here and nothing else:

  MCP tool schema  ->  Anthropic tool definition   (so the model can see them)
  Anthropic tool_use  ->  MCP call_tool            (so the model can run them)

That is the whole adapter. It is worth reading precisely because it is small:
the reason the agent loop needs no framework is that this is all a framework
would be doing at this layer.

The servers run as subprocesses over stdio, exactly as any other MCP host would
run them. Nothing about them is special-cased for this repo — point Claude
Desktop at mcp/k8s_mcp.py and it works there too.
"""

from __future__ import annotations

import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVERS = {
    "k8s": REPO_ROOT / "mcp" / "k8s_mcp.py",
    "prom": REPO_ROOT / "mcp" / "prom_mcp.py",
}


class ToolRegistry:
    """Owns the MCP sessions and routes tool calls to the right server."""

    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._clients: dict[str, Client] = {}
        self._owner: dict[str, str] = {}   # tool name -> server key
        self.definitions: list[dict] = []  # Anthropic tool definitions

    async def __aenter__(self) -> "ToolRegistry":
        # Enter the stack first and unwind it explicitly if anything below
        # fails. Without this, an exception raised here leaves the MCP clients'
        # anyio task groups un-unwound and the process hangs instead of
        # reporting the error — which is a miserable way to discover a one-word
        # typo, and attendees will be editing these files.
        await self._stack.__aenter__()
        try:
            await self._connect_all()
        except BaseException:
            await self._stack.aclose()
            raise
        return self

    async def _connect_all(self) -> None:
        for key, script in SERVERS.items():
            # `python <script>` over stdio — the standard MCP launch, using the
            # same interpreter that is running the agent so the venv is
            # inherited. Note Client() treats a bare string as an HTTP URL; a
            # stdio server has to be handed a transport.
            transport = stdio_client(
                StdioServerParameters(command=sys.executable, args=[str(script)])
            )
            client = Client(transport)
            session = await self._stack.enter_async_context(client)
            self._clients[key] = session

            for tool in (await session.list_tools()).tools:
                self._owner[tool.name] = key
                self.definitions.append({
                    "name": tool.name,
                    # The MCP docstring becomes the Anthropic tool description
                    # verbatim. This is why those docstrings are written the way
                    # they are — they are the prompt, and this line is where
                    # they become one.
                    "description": tool.description or "",
                    "input_schema": tool.input_schema,
                })

    async def __aexit__(self, *exc) -> None:
        await self._stack.aclose()

    async def call(self, name: str, arguments: dict) -> str:
        """Execute one tool call and return its output as text.

        Errors are returned as text rather than raised. The model can reason
        about "ERROR 403 Forbidden" and change approach; it cannot reason about
        a traceback that ended the loop.
        """
        key = self._owner.get(name)
        if key is None:
            return f"ERROR: no such tool {name!r}"
        try:
            result = await self._clients[key].call_tool(name, arguments)
        except Exception as e:
            return f"ERROR calling {name}: {e}"

        parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        text = "\n".join(parts) or "<no output>"
        if getattr(result, "is_error", False):
            return f"ERROR: {text}"
        return text
