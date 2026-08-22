"""The guardrails are the part of this repo that must hold when everything
else is having a bad day, so they are tested directly rather than only through
the agent.

That distinction matters: an agent-level test proves a model chose to behave.
These prove it could not have done otherwise.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.guardrails import Guardrails, WRITE_TOOL_NAMES, tool_definitions  # noqa: E402


@pytest.fixture
def guard_factory(tmp_path, monkeypatch):
    def make(*, allow_writes, approve=None):
        g = Guardrails(allow_writes=allow_writes)
        g.audit.path = tmp_path / "audit.jsonl"
        if approve is not None:
            monkeypatch.setattr(g, "_approve", lambda *a, **k: approve)
        # Never touch a real cluster from a unit test.
        monkeypatch.setattr(g, "_preview", lambda n, a: ("would change X", "- old\n+ new"))
        monkeypatch.setattr(g, "_execute", lambda n, a: "APPLIED: deployment rolled back")
        return g
    return make


def _approvals(guard):
    return [e["approval"] for e in guard.audit.entries()]


def test_write_tools_are_declared_with_dry_run_required():
    """dry_run must be a *required* parameter. If it were optional with a
    default, a model could omit it and the meaning of the call would depend on
    our default rather than on what the model actually asked for."""
    for defn in tool_definitions():
        assert "dry_run" in defn["input_schema"]["required"], defn["name"]


def test_read_only_session_refuses_writes(guard_factory):
    """Criterion 16.7, first clause."""
    g = guard_factory(allow_writes=False)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-prod", "name": "inference-api", "dry_run": False})
    assert out.startswith("REFUSED")
    assert _approvals(g) == ["refused_read_only"]


def test_read_only_refuses_even_a_dry_run_tool_call(guard_factory):
    """Read-only means the write tool does nothing at all, not that it does the
    harmless half. Anything else is a surface to probe."""
    g = guard_factory(allow_writes=False)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-prod", "name": "inference-api", "dry_run": True})
    assert out.startswith("REFUSED")


def test_dry_run_never_reaches_the_gate(guard_factory):
    g = guard_factory(allow_writes=True, approve=False)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-prod", "name": "inference-api", "dry_run": True})
    assert "DRY RUN" in out
    assert _approvals(g) == ["not_required"]


def test_denied_approval_does_not_execute(guard_factory):
    """Criterion 16.7, second clause — the refusal path."""
    g = guard_factory(allow_writes=True, approve=False)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-prod", "name": "inference-api", "dry_run": False})
    assert "DENIED" in out
    assert "APPLIED" not in out
    assert _approvals(g) == ["denied"]


def test_granted_approval_executes_and_is_audited(guard_factory):
    g = guard_factory(allow_writes=True, approve=True)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-prod", "name": "inference-api", "dry_run": False})
    assert "APPLIED" in out
    assert _approvals(g) == ["granted"]


def test_writes_outside_ml_prod_are_refused(guard_factory):
    g = guard_factory(allow_writes=True, approve=True)
    out = g.handle_write("rollback_deployment",
                         {"namespace": "ml-staging", "name": "inference-api", "dry_run": False})
    assert out.startswith("REFUSED")
    assert "granted" not in _approvals(g)


def test_only_a_literal_y_approves(monkeypatch, tmp_path):
    """Not 'yes', not 'Y', not ''. A stray newline must never approve a
    production write."""
    g = Guardrails(allow_writes=True)
    g.audit.path = tmp_path / "audit.jsonl"
    for answer, expected in [("y", True), ("Y", False), ("yes", False),
                             ("", False), (" y", False), ("n", False)]:
        monkeypatch.setattr("builtins.input", lambda _prompt, a=answer: a)
        assert g._approve("rollback_deployment", {}, "d", "diff") is expected, answer


def test_eof_at_the_prompt_is_a_refusal(monkeypatch, tmp_path):
    """A closed stdin — piped input, a CI runner, a detached terminal — must
    fail closed."""
    g = Guardrails(allow_writes=True)
    g.audit.path = tmp_path / "audit.jsonl"

    def boom(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", boom)
    assert g._approve("rollback_deployment", {}, "d", "diff") is False


def test_no_bypass_flag_ships():
    """Criterion: 'No --yes bypass flag in shipped code.'

    Inspects the AST rather than grepping text, so the prose in guardrails.py
    explaining why there is no bypass does not trip the check on itself. Two
    things would constitute a bypass: a CLI flag, or an environment variable
    consulted to skip approval.

    The eval harness's auto_approve_for_tests is a constructor argument, not
    reachable from any CLI, and is deliberately not on this list.
    """
    banned_flags = {"--yes", "-y", "--force", "--no-confirm", "--skip-approval"}
    banned_env = {"SKIP_APPROVAL", "AUTO_APPROVE", "NO_CONFIRM", "FORCE_APPLY"}

    for path in list((REPO / "agent").rglob("*.py")) + list((REPO / "labs").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)

            if name == "add_argument":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and arg.value in banned_flags:
                        raise AssertionError(f"{path.name} declares a bypass flag: {arg.value}")

            # os.environ.get("SKIP_APPROVAL") and friends
            if name == "get":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and arg.value in banned_env:
                        raise AssertionError(f"{path.name} reads a bypass env var: {arg.value}")

        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if node.slice.value in banned_env:
                    raise AssertionError(f"{path.name} reads a bypass env var: {node.slice.value}")


def test_audit_log_is_jsonl_and_records_reads_too(guard_factory):
    g = guard_factory(allow_writes=True, approve=True)
    g.audit.record(tool="list_pods", arguments={"namespace": "ml-prod"},
                   result_summary="3 pods")
    g.handle_write("rollback_deployment",
                   {"namespace": "ml-prod", "name": "inference-api", "dry_run": False})

    lines = g.audit.path.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        entry = json.loads(line)
        assert {"timestamp", "tool", "arguments", "approval", "result_summary"} <= entry.keys()
    assert json.loads(lines[0])["approval"] == "n/a"
    assert json.loads(lines[1])["approval"] == "granted"
