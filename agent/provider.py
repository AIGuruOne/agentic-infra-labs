"""Thin LLM provider seam.

Deliberately thin. This is not a plugin architecture and should not become one
— it exists so the OpenAI path is a readable fallback, not so the repo can
support arbitrary providers. The whole OpenAI translation is the bottom ~40
lines of this file; if it grows much past that, the right move is to delete it
rather than generalise it.

Anthropic is the canonical path. Everything the session teaches — the tool-use
loop, the visible reasoning, the stop_reason handling — is written against the
Messages API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_EFFORT = "medium"


def load_dotenv(path: Path | None = None) -> None:
    """Read .env into the environment without adding a dependency.

    Values already set in the real environment win, so `ANTHROPIC_API_KEY=... make lab2`
    behaves the way anyone would expect.
    """
    path = path or REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        # The shipped .env.example carries placeholders. Treating them as real
        # keys turns a clear "no key configured" message into a 401 halfway
        # through a lab.
        if value in ("sk-ant-...", "sk-..."):
            continue
        os.environ.setdefault(key, value)


class NoCredentials(RuntimeError):
    pass


@dataclass
class Reply:
    """One assistant turn, provider-independent."""

    text: str
    content: list  # raw provider content blocks — the agent loop needs these verbatim
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, effort: str | None = None):
        import anthropic

        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise NoCredentials(
                "ANTHROPIC_API_KEY is not set.\n"
                "  Copy .env.example to .env and add your key, or run with --provider openai."
            )
        self.model = model or os.environ.get("AGENT_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("AGENT_EFFORT") or DEFAULT_EFFORT
        self._client = anthropic.Anthropic()

    def complete(self, *, system, messages, tools=None, max_tokens=8000) -> Reply:
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            # display="summarized" is not the default — on Opus 5 the default is
            # "omitted", which on a screen share renders as a long silent pause
            # before any output. The loop being visible is the lesson, so we ask
            # for the summary explicitly.
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": self.effort},
        )
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in response.content if b.type == "text")
        return Reply(
            text=text,
            content=response.content,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class OpenAIProvider:
    """Documented fallback. Same seam, ~40 lines, not a supported teaching path."""

    name = "openai"

    def __init__(self, model: str | None = None, effort: str | None = None):
        from openai import OpenAI

        load_dotenv()
        if not os.environ.get("OPENAI_API_KEY"):
            raise NoCredentials("OPENAI_API_KEY is not set.")
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o"
        self._client = OpenAI()

    def complete(self, *, system, messages, tools=None, max_tokens=8000) -> Reply:
        oai_messages = [{"role": "system", "content": system}]
        for m in messages:
            content = m["content"]
            if isinstance(content, list):
                content = "".join(
                    b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")
                    for b in content
                )
            oai_messages.append({"role": m["role"], "content": content})

        kwargs = dict(model=self.model, max_tokens=max_tokens, messages=oai_messages)
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": {
                    "name": t["name"], "description": t["description"],
                    "parameters": t["input_schema"]}}
                for t in tools
            ]
        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        return Reply(
            text=choice.message.content or "",
            content=choice.message,
            stop_reason=choice.finish_reason,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
        )


def get_provider(name: str = "anthropic", **kwargs):
    return {"anthropic": AnthropicProvider, "openai": OpenAIProvider}[name](**kwargs)
