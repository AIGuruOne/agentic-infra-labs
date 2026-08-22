"""The agent loop. Raw Anthropic Messages API, no framework.

    observe -> plan -> act -> verify

Roughly forty lines of actual control flow, and they are the point of the
session. Everything a framework gives you at this layer is: this while loop,
the tool-result plumbing in agent/tools.py, and an iteration cap. Seeing it
written out is what makes the LangGraph port in /alt meaningful later — you
cannot appreciate what an abstraction removes until you have seen what it was
abstracting.

Each step prints as it happens: reasoning, tool call, tool result summary. On a
screen share the loop being *visible* is the lesson, so this deliberately does
not buffer and does not hide the intermediate turns.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from agent.provider import get_provider
from agent.tools import ToolRegistry

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
CYAN, GREEN, YELLOW, RED = "\033[36m", "\033[32m", "\033[33m", "\033[31m"

MAX_ITERATIONS = 12

SYSTEM = """You are an infrastructure engineering agent investigating a live Kubernetes cluster.

You have read-only tools over Kubernetes and Prometheus, and a corpus of runbooks
retrieved for you and included below.

How to work:

- Establish what is true from the LIVE CLUSTER before you conclude anything.
  The runbooks describe what usually happens; the cluster tells you what did.
- Investigate before you answer. A first plausible cause is a hypothesis, not a
  diagnosis. Check it.
- When a failure could have more than one cause, look for all of them. Scheduler
  events in particular list every reason at once — read the whole message.
- Cite the runbook ID, like [RB-014], for any remediation you propose, and check
  that the runbook you cite matches the environment you are investigating. A
  runbook written for staging can be exactly wrong in production.
- If the evidence does not support a conclusion, say what you would need to see
  rather than guessing.

Finish with:

  ROOT CAUSE     what is actually wrong, and the evidence from the cluster
  REMEDIATION    what to do, with the concrete commands, and the runbook cited
  CONFIDENCE     high / medium / low, and what would change it

You cannot make changes. Propose remediation; do not attempt to apply it.
"""

# Appended when Lab 3 registers the write tools. Kept separate rather than
# folded into SYSTEM so the read-only default is the literal default: a session
# that does not opt in is never told it can act.
WRITES_ENABLED_SYSTEM = """

You also have write tools this session, and they are gated.

Work in this order, every time:

1. Diagnose from live cluster state first. Never propose a change you have not
   established the need for.
2. Call the write tool with dry_run=true and read what it reports back. The dry
   run tells you which revision would be restored and what image it carries.
3. If the dry run confirms your diagnosis, you MUST call the SAME tool again
   with dry_run=false to request the change for real. Do not stop after the dry
   run, and do not answer with the equivalent kubectl command for a human to
   run by hand — that is not what you were asked to do, and it routes the
   change around the audit log.

Step 3 does not apply the change. It presents the exact diff to a human
operator, who approves or refuses it. Expect to be refused sometimes; that is
the system working. If you are refused, say what you would have done and stop —
do not retry, and do not look for another route to the same change.
"""


@dataclass
class Result:
    answer: str
    iterations: int
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def tools_used(self) -> list[str]:
        return [c["name"] for c in self.tool_calls]


def _summarize(text: str, limit: int = 240) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[:limit] + f" … (+{len(flat) - limit} chars)"


async def investigate(
    question: str,
    *,
    context: str = "",
    provider_name: str = "anthropic",
    max_iterations: int = MAX_ITERATIONS,
    quiet: bool = False,
    system_extra: str = "",
    extra_tools: list | None = None,
    tool_dispatch=None,
) -> Result:
    """Run the agent loop until the model stops asking for tools.

    `extra_tools` / `tool_dispatch` are how Lab 3 adds gated write tools without
    this file needing to know anything about approval gates.
    """
    provider = get_provider(provider_name)

    def say(*a, **k):
        if not quiet:
            print(*a, **k, flush=True)

    async with ToolRegistry() as registry:
        definitions = registry.definitions + list(extra_tools or [])
        prompt = f"{context}\n\n{question}" if context else question
        messages: list[dict] = [{"role": "user", "content": prompt}]
        result = Result(answer="", iterations=0)

        say(f"\n{BOLD}question{RESET} {question}")
        say(f"{DIM}model: {provider.model} · tools: {len(definitions)} · max {max_iterations} iterations{RESET}")

        for step in range(1, max_iterations + 1):
            result.iterations = step
            reply = provider.complete(system=SYSTEM + system_extra,
                                      messages=messages, tools=definitions)
            result.input_tokens += reply.input_tokens
            result.output_tokens += reply.output_tokens

            # Show the model's reasoning and narration for this step. This is
            # the part that makes the loop legible rather than magical.
            if reply.thinking.strip():
                say(f"\n{DIM}[{step}] thinking: {_summarize(reply.thinking, 300)}{RESET}")
            if reply.text.strip():
                say(f"\n{BOLD}[{step}]{RESET} {reply.text.strip()}")

            if not reply.wants_tools:
                result.answer = reply.text.strip()
                say(f"\n{DIM}done in {step} iteration(s) · "
                    f"{result.input_tokens} in / {result.output_tokens} out{RESET}\n")
                return result

            # The assistant turn is replayed verbatim, thinking blocks and tool
            # ids and all. Reconstructing it from the text alone breaks the loop.
            messages.append(reply.assistant_message)

            outputs: list[tuple[str, str]] = []
            for call in reply.tool_calls:
                say(f"  {CYAN}-> {call.name}{RESET}"
                    f"{DIM}({', '.join(f'{k}={v!r}' for k, v in call.arguments.items())}){RESET}")

                if tool_dispatch is not None:
                    output = await tool_dispatch(call.name, call.arguments, registry)
                else:
                    output = await registry.call(call.name, call.arguments)

                result.tool_calls.append({"name": call.name, "arguments": call.arguments})
                colour = RED if output.startswith("ERROR") else GREEN
                say(f"     {colour}{_summarize(output)}{RESET}")
                outputs.append((call.id, output))

            messages.extend(provider.tool_result_messages(outputs))

        result.answer = (
            f"Stopped after {max_iterations} iterations without reaching a conclusion. "
            "Investigated: " + ", ".join(dict.fromkeys(result.tools_used))
        )
        say(f"\n{YELLOW}{result.answer}{RESET}\n")
        return result


def run(question: str, **kwargs) -> Result:
    """Synchronous entry point."""
    return asyncio.run(investigate(question, **kwargs))
