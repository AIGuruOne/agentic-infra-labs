"""Append-only audit log.

Every tool the agent invokes lands here — reads included, not just writes. A log
that records only the dangerous operations cannot answer "what did it look at
before it decided that", which is the question you actually have at 3am.

JSONL because it is appendable, greppable, and survives a crash mid-write with
at most one bad line. `make lab3` tails it in a second pane so the audit trail
is visible while the agent is working rather than reconstructed afterwards.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "audit.jsonl"


class AuditLog:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or os.environ.get("AUDIT_LOG", DEFAULT_PATH))

    def record(
        self,
        *,
        tool: str,
        arguments: dict,
        result_summary: str,
        approval: str = "n/a",
        dry_run: bool = False,
    ) -> None:
        """One line per tool call.

        `approval` is one of: n/a (a read), granted, denied, not_required
        (a dry run), or refused_read_only (blocked before it was ever offered
        to a human).
        """
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "tool": tool,
            "arguments": arguments,
            "dry_run": dry_run,
            "approval": approval,
            "result_summary": " ".join(result_summary.split())[:400],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out
