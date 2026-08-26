#!/usr/bin/env python3
"""The same agent, expressed in LangGraph. A reference port, not a second path.

Frozen at `packt-aug-2026`. Not covered by CI. Read `README.md` in this
directory before running it.

The point of this file is comparison, so read it against `agent/loop.py`.

What the framework removes:

    the loop            `while stop_reason == "tool_use"` — gone
    history plumbing    appending the assistant turn verbatim, batching every
                        tool_result into one user message — gone
    the iteration cap   `recursion_limit` instead of `for step in range(...)`
    provider shape      one class swap instead of a normalised Reply dataclass

That is a real saving. In `agent/loop.py` it is about forty lines, and every one
of them is a line you could get wrong. We got two of them wrong while building
this repo: replaying the assistant turn from text rather than verbatim, and
splitting tool results across messages.

What the framework costs, and what you should weigh:

    You cannot see the loop. The lesson of Segment 4 is that the loop is small
    and knowable. Once it is `create_react_agent(...)`, it is neither.

    You inherit its dependency graph. This directory's venv resolves
    anthropic==0.125.0 — the 0.x line — because langchain-anthropic pins it,
    while /labs runs anthropic==1.0.0. That is why this port has its own venv:
    installing it beside /labs would silently downgrade the canonical path.

    You inherit its release cadence. This file worked against langgraph 1.2.11
    on 27 August 2026. If it does not work against yours, that is expected —
    see README.md.

Everything else is deliberately identical to the canonical path: the same MCP
servers, the same runbook retrieval, the same system prompt, the same scenario.
The only variable is the loop.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import warnings
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab1-knowledge-layer"))

from langchain_anthropic import ChatAnthropic          # noqa: E402
from langchain_core.tools import StructuredTool        # noqa: E402
# langgraph 1.2 deprecates this in favour of `langchain.agents.create_agent`,
# which lives in a package this port does not depend on. Importing the
# deprecated name and silencing the warning is the honest choice for a frozen
# reference: chasing the rename would mean adding another dependency to a
# directory whose entire point is that it is not maintained. The deprecation is
# itself the exhibit — this file is four months old.
warnings.filterwarnings("ignore", message=".*create_react_agent has been moved.*")
from langgraph.prebuilt import create_react_agent      # noqa: E402

from agent.loop import SYSTEM                          # noqa: E402  same prompt, verbatim
from agent.provider import DEFAULT_MODEL, load_dotenv  # noqa: E402
from agent.tools import ToolRegistry                   # noqa: E402  same MCP servers
from retrieval import load_corpus, search              # noqa: E402  same retrieval

BOLD, DIM, RESET, CYAN = "\033[1m", "\033[2m", "\033[0m", "\033[36m"

SCENARIOS = {
    1: ("Why are the model-serving pods in ml-prod repeatedly restarting?", "prod", "ml-prod"),
    2: ("How do I troubleshoot the GPU scheduling failure in ml-prod? A pod is stuck Pending.",
        "prod", "ml-prod"),
}


def as_langchain_tools(registry: ToolRegistry) -> list[StructuredTool]:
    """Wrap the MCP tools as LangChain tools.

    This adapter is the honest cost of the port. `agent/tools.py` already
    translates MCP into the Anthropic tool shape; here that translation happens
    again, into a third shape. The MCP docstrings still carry the descriptions —
    they remain the prompt, exactly as in the canonical path.
    """
    tools = []
    for definition in registry.definitions:
        name = definition["name"]

        def make(tool_name: str):
            async def call(**kwargs) -> str:
                return await registry.call(tool_name, kwargs)
            return call

        tools.append(StructuredTool.from_function(
            coroutine=make(name),
            name=name,
            description=definition["description"],
            args_schema=definition["input_schema"],
        ))
    return tools


def extract_text(message) -> str:
    """Pull the human-readable answer out of a LangChain message.

    `.content` is a list of content blocks on a thinking-enabled model, not a
    string, so printing it directly dumps thinking signatures and base64 into
    the terminal. The canonical path never has this problem because
    agent/provider.py normalises the reply into a text field at the seam.

    A small thing, and a fair illustration of the trade: the framework hands
    back its own message type, and you learn its shape the first time you print
    one in front of an audience.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p.strip()) or "<no text in final message>"


async def main() -> int:
    ap = argparse.ArgumentParser(description="LangGraph reference port — frozen, unmaintained")
    ap.add_argument("--scenario", type=int, default=1, choices=sorted(SCENARIOS))
    ap.add_argument("--max-iterations", type=int, default=12)
    args = ap.parse_args()

    load_dotenv()
    question, environment, namespace = SCENARIOS[args.scenario]

    corpus = load_corpus()
    hits = search(question, corpus, environment=environment, namespace=namespace, top_k=3)
    print(f"\n{BOLD}runbooks retrieved{RESET}")
    for h in hits:
        print(f"  {h.runbook.id}  score {h.score:5.2f}  {DIM}{h.runbook.title}{RESET}")
    context = "Runbooks retrieved for this incident:\n" + "".join(
        f"\n--- {h.runbook.id} (environment={h.runbook.meta.get('environment')}) ---\n"
        f"{h.runbook.body.strip()}\n" for h in hits
    )

    async with ToolRegistry() as registry:
        model = ChatAnthropic(model=DEFAULT_MODEL, max_tokens=8000)

        # This single call replaces agent/loop.py's investigate(). That is the
        # entire teaching point of this directory.
        agent = create_react_agent(model, as_langchain_tools(registry), prompt=SYSTEM)

        print(f"\n{BOLD}question{RESET} {question}")
        print(f"{DIM}langgraph create_react_agent · {len(registry.definitions)} tools{RESET}\n")

        final = None
        async for chunk in agent.astream(
            {"messages": [("user", f"{context}\n\n{question}")]},
            {"recursion_limit": args.max_iterations * 2},
            stream_mode="values",
        ):
            final = chunk
            message = chunk["messages"][-1]
            for tc in getattr(message, "tool_calls", None) or []:
                args_str = ", ".join(f"{k}={v!r}" for k, v in tc["args"].items())
                print(f"  {CYAN}-> {tc['name']}{RESET}{DIM}({args_str}){RESET}")

        print(f"\n{BOLD}answer{RESET}\n")
        print(extract_text(final["messages"][-1]) if final else "<no answer>")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
