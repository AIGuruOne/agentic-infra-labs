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


def test_pod_logs_are_unwrapped_not_a_bytes_repr():
    """kubernetes==36.0.3 returns pod logs as a str containing the repr of
    bytes. The agent reads whatever this returns, so if it is not unwrapped the
    model gets escaped \\n instead of line breaks."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("k8s_mcp", REPO / "mcp" / "k8s_mcp.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    wrapped = 'b"FATAL: model config not found\\nFATAL: cannot start.\\n"'
    cleaned = module._clean_logs(wrapped)
    assert not cleaned.startswith('b"')
    assert "\n" in cleaned
    assert "\\n" not in cleaned
    assert module._clean_logs("ordinary log line") == "ordinary log line"
    assert module._clean_logs(b"raw bytes\n") == "raw bytes\n"


def test_mcp_servers_receive_the_env_vars_they_read():
    """The MCP SDK does not pass the parent environment to a stdio server — its
    default allow-list is HOME/LOGNAME/PATH/SHELL/TERM/USER and everything else
    is dropped silently.

    Both of our documented escape hatches are environment variables, so without
    explicit forwarding, setting them did nothing and reported nothing:
    PROMETHEUS_URL (how CI reaches Prometheus without a port-forward) and
    AGENT_KUBECONFIG (how you point the tools at your own cluster).
    """
    import os
    import sys

    sys.path.insert(0, str(REPO))
    from agent.tools import FORWARDED_ENV, server_environment

    previous = {k: os.environ.get(k) for k in FORWARDED_ENV}
    try:
        for key in FORWARDED_ENV:
            os.environ[key] = f"sentinel-{key}"
        env = server_environment()
        for key in FORWARDED_ENV:
            assert env.get(key) == f"sentinel-{key}", f"{key} is not forwarded to MCP servers"
        assert "PATH" in env, "the SDK's own safe defaults were dropped"
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_unset_env_vars_are_not_forwarded_as_empty():
    """Forwarding an unset variable as "" would override the server's own
    default with an empty path, which fails in a far more confusing way than
    not setting it at all."""
    import os
    import sys

    sys.path.insert(0, str(REPO))
    from agent.tools import server_environment

    previous = os.environ.pop("PROMETHEUS_URL", None)
    try:
        assert "PROMETHEUS_URL" not in server_environment()
    finally:
        if previous is not None:
            os.environ["PROMETHEUS_URL"] = previous


def test_list_services_does_not_require_cluster_wide_permission():
    """The agent's Role is namespaced to ml-prod and ml-staging by design, so a
    cluster-wide Service list is forbidden. The tool must degrade to the
    namespaces it can see AND say that it did — an agent silently seeing less
    than it asked for concludes "no such service exists elsewhere" when the
    truth is "I was not allowed to look"."""
    source = (REPO / "mcp" / "k8s_mcp.py").read_text()
    assert "SCOPED_NAMESPACES" in source
    assert "_services_everywhere_visible" in source
    assert "not permitted to list Services" in source, \
        "the fallback must report reduced scope, not hide it"


def test_agent_role_grants_no_cluster_wide_service_read():
    """Guard the blast radius: if someone 'fixes' the tool above by widening
    RBAC instead, this fails. The only cluster-scoped grant is nodes, which
    scenario 02 genuinely needs."""
    import yaml

    docs = [d for d in yaml.safe_load_all((REPO / "cluster" / "rbac" / "agent-sa.yaml").read_text()) if d]
    cluster_roles = [d for d in docs if d.get("kind") == "ClusterRole"]
    granted = {r for cr in cluster_roles for rule in cr.get("rules", []) for r in rule.get("resources", [])}
    assert granted == {"nodes"}, f"cluster-scoped grants widened to {granted}"


def test_manifests_declare_every_env_var_the_faults_set():
    """`kubectl set env` does not update last-applied-configuration, so a
    three-way merge emits no delete directive for an env entry that exists only
    in the live object. Any variable a break script sets that the manifest does
    not declare survives `make reset` forever.

    This shipped: break-4's CPU_BURN_MS persisted, so prod burned 250ms of CPU
    per request permanently, the "baseline" p95 sat at 488ms instead of 24ms,
    and scenario 04's latency step-change could never be observed.
    """
    import re

    manifest = (REPO / "workloads" / "manifests" / "10-inference-prod.yaml").read_text()
    declared = set(re.findall(r"- name: ([A-Z_][A-Z0-9_]*)\n\s+value:", manifest))

    set_by_faults = set()
    for script in (REPO / "faults").glob("break-*.sh"):
        for block in re.findall(r"set env deployment/inference-api([^\n]*(?:\\\n[^\n]*)*)",
                                script.read_text()):
            set_by_faults |= set(re.findall(r"([A-Z_][A-Z0-9_]*)=", block))

    prod_vars = {v for v in set_by_faults if v not in ("MODEL_NAME",)}
    missing = prod_vars - declared
    assert not missing, (
        f"break scripts set {sorted(missing)} but the prod manifest does not "
        f"declare them, so `make reset` cannot remove them"
    )


def test_stub_tool_is_not_advertised_until_enabled():
    """A tool registered but returning 'not implemented' is still offered to the
    model, which calls it, reads the apology, and has spent an iteration and a
    few thousand tokens learning nothing."""
    source = (REPO / "mcp" / "k8s_mcp.py").read_text()
    live = [ln for ln in source.splitlines()
            if ln.strip().startswith("def get_resource_quota")]
    assert not live, "get_resource_quota is registered; it should stay commented until the exercise"
    assert "# @server.tool()" in source, "the exercise block is missing"


def test_optional_provider_is_pinned_like_everything_else():
    """README calls --provider openai 'a real, tested fallback rather than an
    aspiration'. An unpinned optional dep makes that true only on the machine it
    was developed on."""
    text = (REPO / "requirements.txt").read_text()
    assert re.search(r"^openai==", text, re.M), "openai is not pinned in requirements.txt"


def test_k8s_mcp_imports_without_any_kubeconfig():
    """Import runs config loading. Raising there kills the MCP subprocess during
    startup and the caller sees an opaque handshake failure instead of 'run make
    cluster first' — the exact situation of a Tier B attendee or a fresh CI
    runner, neither of which has a kubeconfig."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-c",
         "import importlib.util;"
         f"spec=importlib.util.spec_from_file_location('k',{str(REPO / 'mcp' / 'k8s_mcp.py')!r});"
         "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);"
         "print('CONFIG_ERROR' if m.CONFIG_ERROR else 'loaded')"],
        capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": "/nonexistent",
             "AGENT_KUBECONFIG": "/nonexistent"},
    )
    assert proc.returncode == 0, f"import raised without a kubeconfig:\n{proc.stderr[-600:]}"


def test_readme_bringup_time_matches_versions():
    """Commit 87dadda corrected VERSIONS and missed the README."""
    readme = (REPO / "README.md").read_text()
    assert "~45 seconds" not in readme, \
        "README still claims the reuse time (45s) for the from-clean path"


def test_setup_does_not_abort_without_docker():
    """The README's central Tier B promise is that Lab 1 needs nothing but
    Python. setup.sh used to `die` the moment Docker was unreachable — before
    creating the venv — so the very attendee the error message was reassuring
    ended up with no rank_bm25 and no PyYAML, and Lab 1 could not run at all.

    Docker must be a warning here, and the venv must still be built.
    """
    source = (REPO / "scripts" / "setup.sh").read_text()

    docker_section = source[source.index('say "docker"'):source.index('say "python"')]
    assert "die " not in docker_section, \
        "setup.sh aborts when Docker is missing; Tier B never reaches the venv step"
    assert "warn " in docker_section, "a missing Docker should warn, not pass silently"

    # The venv must be created after the Docker check, not gated behind it.
    assert source.index('say "python"') > source.index('say "docker"')
    assert "-m venv .venv" in source


def test_lab1_imports_need_no_cluster_libraries():
    """Lab 1's promise is Python-only. If it ever imports the kubernetes client
    or the MCP SDK at module scope, a Tier B attendee gets an ImportError
    instead of a lesson."""
    import ast as _ast

    for path in [REPO / "labs" / "lab1-knowledge-layer" / "retrieval.py",
                 REPO / "labs" / "lab1-knowledge-layer" / "ask.py"]:
        tree = _ast.parse(path.read_text())
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                # module-scope imports only
                names = [a.name for a in node.names] if isinstance(node, _ast.Import) \
                    else [node.module or ""]
                for name in names:
                    assert not name.startswith(("kubernetes", "mcp")), \
                        f"{path.name} imports {name}, which Lab 1 must not require"


def test_documented_tool_count_matches_reality():
    """The README, the deck and Lab 2's EXPECTED.md all state a tool count.
    Unregistering get_resource_quota during review made every one of them wrong,
    and nothing complained."""
    import re as _re

    k8s = (REPO / "mcp" / "k8s_mcp.py").read_text()
    prom = (REPO / "mcp" / "prom_mcp.py").read_text()
    # a live tool is a @server.tool() that is not commented out
    live = sum(1 for src in (k8s, prom)
               for ln in src.splitlines() if ln.strip() == "@server.tool()")

    readme = (REPO / "README.md").read_text()
    claimed = _re.search(r"Prometheus, (\d+) tools\)", readme)
    assert claimed, "README no longer states a tool count"
    assert int(claimed.group(1)) == live, (
        f"README claims {claimed.group(1)} tools; the servers register {live}"
    )
