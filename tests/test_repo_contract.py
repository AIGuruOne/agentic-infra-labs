"""Contract tests for the things a Tier B or Tier C attendee depends on.

These are cheap and they catch the failure that is hardest to notice: a repo
that works perfectly on the machine it was built on, and not on a fresh clone.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]


def test_every_lab_has_expected_output():
    """Criterion 16.9. Tier C reads the repo without running it; a lab with no
    EXPECTED.md is invisible to them."""
    labs = sorted(p for p in (REPO / "labs").iterdir() if p.is_dir())
    assert len(labs) == 4
    for lab in labs:
        expected = lab / "EXPECTED.md"
        assert expected.exists(), f"{lab.name} has no EXPECTED.md"
        assert len(expected.read_text().split()) > 200, f"{lab.name}/EXPECTED.md is a stub"


def test_all_scripts_are_executable_and_valid_bash():
    for script in list((REPO / "scripts").rglob("*.sh")) + \
                  list((REPO / "faults").glob("*.sh")) + \
                  list((REPO / "cluster").rglob("*.sh")):
        if script.name in ("pick-python.sh", "lib.sh"):   # sourced, not executed
            continue
        mode = script.stat().st_mode
        assert mode & stat.S_IXUSR, f"{script.relative_to(REPO)} is not executable"
        proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{script.name}: {proc.stderr}"


def test_seven_faults_and_a_reset_exist():
    for i in range(1, 8):
        assert (REPO / "faults" / f"break-{i}.sh").exists()
    assert (REPO / "faults" / "reset.sh").exists()


def test_each_break_script_announces_exactly_once():
    """Every break prints exactly two lines: what was injected, and the question
    to ask. On a screen share, every extra line is a line the audience has to
    decide to ignore."""
    for i in range(1, 8):
        text = (REPO / "faults" / f"break-{i}.sh").read_text()
        assert text.count("announce ") == 1, f"break-{i}.sh calls announce {text.count('announce ')} times"
        assert "echo " not in text.replace("#", ""), f"break-{i}.sh echoes outside announce"


def test_makefile_exposes_the_documented_ux():
    text = (REPO / "Makefile").read_text()
    for target in ["doctor", "setup", "cluster", "verify", "reset", "clean",
                   "lab1", "lab2", "lab3", "lab4", "test"]:
        assert re.search(rf"^{target}:", text, re.M), f"Makefile has no '{target}' target"
    assert "break-%:" in text


def test_env_example_has_no_real_key():
    """A .env.example that has been filled in and committed is the worst
    possible bug in a repository that gets sold."""
    text = (REPO / ".env.example").read_text()
    assert re.search(r"ANTHROPIC_API_KEY=sk-ant-\.\.\.", text)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", text), "a real Anthropic key is in .env.example"
    assert not re.search(r"sk-[A-Za-z0-9]{32,}", text), "a real key is in .env.example"


def test_gitignore_covers_secrets_and_runtime_output():
    text = (REPO / ".gitignore").read_text()
    for pattern in [".env", "audit.jsonl", "agent.kubeconfig"]:
        assert pattern in text, f".gitignore does not cover {pattern}"


def test_no_secrets_are_tracked_by_git():
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO,
                             capture_output=True, text=True).stdout.split()
    for path in tracked:
        assert not path.endswith(".env"), f"{path} is tracked"
        assert "agent.kubeconfig" not in path, f"{path} is tracked"
        assert not path.endswith("audit.jsonl"), f"{path} is tracked"


def test_eval_cases_are_wellformed_and_case_8_is_the_trap():
    cases = yaml.safe_load((REPO / "labs" / "lab4-evals" / "cases.yaml").read_text())["cases"]
    assert len(cases) == 8

    expected_failures = [c for c in cases if c.get("expect_fail")]
    assert len(expected_failures) == 1, "there should be exactly one designed-to-fail case"
    trap = expected_failures[0]
    assert trap["no_metadata_filter"] is True
    assert "delete configmap" in [s.lower() for s in trap["assert"]["must_not_contain"]]

    # The trap must be the same question as a passing case, or it proves nothing.
    twin = next(c for c in cases if c["id"] == "case-01-crashloop")
    assert trap["question"] == twin["question"]
    assert trap["assert"] == twin["assert"]


def test_requirements_are_fully_pinned():
    for line in (REPO / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "==" in line, f"unpinned dependency: {line}"


@pytest.mark.parametrize("doc", ["README.md", "VERSIONS.md", "LICENSE.md"])
def test_top_level_docs_exist(doc):
    assert (REPO / doc).exists()


def test_readme_leads_with_tiers_not_installation():
    """The README's job is to make 'I'm falling behind' impossible before it
    starts. That means the tier question comes before the install steps."""
    text = (REPO / "README.md").read_text()
    tier_pos = text.find("Which tier are you?")
    quickstart_pos = text.find("## Quickstart")
    assert tier_pos != -1, "README does not ask which tier the reader is"
    assert tier_pos < quickstart_pos, "installation comes before the tier question"


def test_no_agent_framework_in_labs_or_agent():
    """Constraint: the canonical path is the raw API plus the MCP SDK. No
    framework anywhere outside /alt."""
    banned = ("langchain", "langgraph", "llama_index", "crewai", "autogen", "haystack")
    for path in list((REPO / "labs").rglob("*.py")) + list((REPO / "agent").rglob("*.py")) + \
                list((REPO / "mcp").rglob("*.py")):
        low = path.read_text(encoding="utf-8").lower()
        for framework in banned:
            assert f"import {framework}" not in low and f"from {framework}" not in low, \
                f"{path.name} imports {framework}"
