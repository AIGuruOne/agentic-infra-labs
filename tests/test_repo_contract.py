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


def test_glossary_promises_no_flag_that_does_not_exist():
    """The glossary is read by attendees who will then type what it mentions.
    An earlier draft said dense retrieval was "available behind --dense"; the
    flag does not exist and argparse rejects it."""
    import subprocess
    import sys

    glossary = (REPO / "GLOSSARY.md").read_text()
    flags = set(re.findall(r"`(--[a-z-]+)`", glossary))
    if not flags:
        return

    helps = ""
    for script in ["labs/lab1-knowledge-layer/ask.py",
                   "labs/lab2-live-state-agent/investigate.py",
                   "labs/lab3-guardrails/remediate.py",
                   "labs/lab4-evals/run_evals.py"]:
        helps += subprocess.run([sys.executable, str(REPO / script), "--help"],
                                capture_output=True, text=True).stdout

    for flag in flags:
        assert flag in helps, f"GLOSSARY.md mentions {flag}, which no lab accepts"


def test_alt_is_isolated_from_the_canonical_path():
    """Constraint from the build spec: /labs is canonical and CI-tested; /alt is
    a frozen reference. Nothing in the supported path may depend on the port,
    and the port's dependencies must never leak into the main requirements —
    langchain-anthropic pins anthropic 0.x, which would silently downgrade the
    canonical path.
    """
    alt = REPO / "alt" / "langgraph"
    assert (alt / "README.md").exists(), "the port must ship its disclaimer"
    assert (alt / "requirements.txt").exists(), "the port must pin what it was verified against"

    main_reqs = (REPO / "requirements.txt").read_text().lower()
    for package in ("langgraph", "langchain"):
        assert package not in main_reqs, f"{package} leaked into the canonical requirements"

    # /labs, /agent and /mcp must not IMPORT the port or the framework. They may
    # mention it in prose — agent/loop.py explains what the port exists to show,
    # and that comment is doing useful work.
    import ast as _ast

    for path in list((REPO / "labs").rglob("*.py")) + list((REPO / "agent").rglob("*.py")) \
            + list((REPO / "mcp").rglob("*.py")):
        tree = _ast.parse(path.read_text())
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, _ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith(("langgraph", "langchain")), \
                    f"{path.name} imports {name} — the canonical path must not depend on the port"

    # The port pins the versions it was verified against, not floating ranges.
    for line in (alt / "requirements.txt").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            assert "==" in line, f"unpinned dependency in the frozen port: {line}"


def test_alt_readme_states_it_is_unmaintained():
    """Framing from the build spec: future breakage must be a documented
    expectation, not a defect someone can refund over."""
    text = " ".join((REPO / "alt" / "langgraph" / "README.md").read_text().lower().split())
    for phrase in ("frozen", "not maintained", "not covered by ci",
                   "expected, not a defect"):
        assert phrase in text, f"the port's README does not say {phrase!r}"


def test_licence_is_mit_and_carves_out_vendored_code():
    """The repo is MIT, but observability/metrics-server.yaml is vendored from
    kubernetes-sigs/metrics-server under Apache 2.0. A blanket MIT grant would
    purport to relicense someone else's file."""
    # The plain LICENSE file is what GitHub's detector reads and what puts the
    # MIT badge on the repository; LICENSE.md carries the longer notices.
    plain = (REPO / "LICENSE").read_text()
    assert plain.lstrip().startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in plain
    assert "WITHOUT WARRANTY OF ANY KIND" in plain
    # The plain LICENSE must stay verbatim MIT and nothing else. GitHub's
    # detector scores against the exact licence body, and a trailing custom note
    # drops it below the match threshold — the repo then shows "NOASSERTION"
    # instead of an MIT badge. Third-party notices live in LICENSE.md.
    assert "metrics-server" not in plain, \
        "LICENSE must be verbatim MIT; put third-party notices in LICENSE.md"
    assert plain.rstrip().endswith("SOFTWARE.")

    licence = (REPO / "LICENSE.md").read_text()
    assert "MIT License" in licence
    assert "Permission is hereby granted, free of charge" in licence

    assert "Apache License" in licence and "metrics-server" in licence, \
        "LICENSE.md does not carve out the vendored Apache-2.0 manifest"

    vendored = (REPO / "observability" / "metrics-server.yaml").read_text()
    assert "Apache License" in vendored, "the vendored file carries no attribution header"
    assert "THIRD-PARTY" in vendored


def test_licence_reserves_the_trademark():
    """MIT grants rights to software, not to marks. AI Guru is registered."""
    licence = (REPO / "LICENSE.md").read_text()
    assert "Trademark" in licence or "trademark" in licence
    assert "AI Guru" in licence


def test_no_placeholder_licence_text_ships():
    """The previous LICENSE.md carried a visible 'replace this before
    publishing' note. Shipping that publicly would be worse than shipping
    nothing."""
    licence = (REPO / "LICENSE.md").read_text().lower()
    for phrase in ("note for the repository owner", "counsel-approved",
                   "replace it with", "placeholder", "todo"):
        assert phrase not in licence, f"LICENSE.md still contains placeholder text: {phrase!r}"


def test_ci_exists_because_the_syllabus_promises_it():
    """"The complete lab repository — version-pinned, CI-tested" is a takeaway
    on the syllabus. It has to be true."""
    workflows = REPO / ".github" / "workflows"
    assert (workflows / "ci.yml").exists()
    assert (workflows / "weekly.yml").exists()


def test_ci_never_touches_the_frozen_port():
    """Build-spec constraint: CI runs against /labs only, never /alt. Testing
    the port here would either drag langchain into the job or create a
    maintenance obligation the port explicitly disclaims."""
    for name in ("ci.yml", "weekly.yml"):
        text = (REPO / ".github" / "workflows" / name).read_text()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue          # prose explaining the exclusion is fine
            assert "alt/langgraph" not in stripped, f"{name} references the frozen port"


def test_ci_tests_the_full_supported_python_range():
    """doctor.sh and setup.sh accept 3.11-3.13. CI must actually prove all
    three, or the range is an untested claim."""
    import yaml as _yaml

    ci = _yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text())
    versions = ci["jobs"]["tests"]["strategy"]["matrix"]["python-version"]
    assert set(versions) == {"3.11", "3.12", "3.13"}, versions


def test_every_advertised_metadata_field_is_filterable():
    """The syllabus promises retrieval aware of "environment, cluster,
    namespace, service, model, GPU type, provider, and region". Only three of
    the eight were wired up; the other five sat in the frontmatter unused."""
    import sys as _sys

    _sys.path.insert(0, str(REPO / "labs" / "lab1-knowledge-layer"))
    from retrieval import FILTERABLE_FIELDS, load_corpus, search

    advertised = {"environment", "cluster", "namespace", "service",
                  "model", "gpu_type", "provider", "region"}
    assert advertised == set(FILTERABLE_FIELDS), \
        f"advertised but not filterable: {sorted(advertised - set(FILTERABLE_FIELDS))}"

    corpus = load_corpus()
    for field in FILTERABLE_FIELDS:
        assert field in corpus[0].meta, f"{field} is filterable but absent from frontmatter"

        # Filtering on a value nothing declares must exclude every runbook that
        # states a concrete value for that field. Runbooks with `null` survive
        # on purpose — null means "applies regardless", and dropping them would
        # be worse than not filtering, since most runbooks are not GPU-specific.
        survivors = search("anything", corpus, top_k=99, **{field: "__nonexistent__"})
        for hit in survivors:
            assert hit.runbook.meta.get(field) is None, (
                f"filtering {field}=__nonexistent__ kept {hit.runbook.id}, which "
                f"declares {field}={hit.runbook.meta.get(field)!r}"
            )


def test_unknown_filter_field_is_rejected_loudly():
    """A typo'd constraint that silently returns the unfiltered corpus is the
    worst possible failure for this particular filter."""
    import sys as _sys

    import pytest as _pytest

    _sys.path.insert(0, str(REPO / "labs" / "lab1-knowledge-layer"))
    from retrieval import apply_metadata_filter, load_corpus

    with _pytest.raises(ValueError):
        apply_metadata_filter(load_corpus(), environmnet="prod")


def test_python_version_discrepancy_is_documented_where_learners_hit_it():
    """The published session description says "Python 3.11+"; the repo needs
    3.11-3.13. The description cannot be changed after publication, so the repo
    has to own the discrepancy — and in both places a learner will look: the
    README before they start, and doctor.sh at the moment it fails them.
    """
    readme = (REPO / "README.md").read_text()
    assert "3.11+" in readme, "README does not acknowledge the published wording"
    assert "not 3.14" in readme.lower()
    assert "not a fault on your machine" in readme.lower(), \
        "the README states the constraint but does not reassure"

    doctor = (REPO / "scripts" / "doctor.sh").read_text()
    assert "3.11+" in doctor, "doctor.sh does not reconcile with the published wording"
    assert "not 3.14" in doctor.lower()
    assert "python@3.12" in doctor, "doctor.sh does not tell the reader how to fix it"


def test_readme_carries_the_prep_guidance_learners_need_days_ahead():
    """Two prerequisites cannot be satisfied on the morning: an API key with
    credit, and permission to run Docker on a managed laptop."""
    readme = (REPO / "README.md").read_text().lower()
    assert "start them now" in readme
    assert "whether policy permits it" in readme, \
        "README does not distinguish 'Docker installed' from 'Docker allowed'"


def test_lab2_reference_solution_is_valid_and_self_consistent():
    """Lab 2 ships a worked solution for the write-your-own exercise. A lab
    answer that does not run is worse than no answer, and it would rot silently
    the first time k8s_mcp.py's helpers were renamed.

    Parses it and checks every name it depends on still exists in the server.
    (Executing it needs a live cluster, so that check lives in CI's smoke job.)
    """
    import ast as _ast
    import re as _re

    doc = (REPO / "labs" / "lab2-live-state-agent" / "EXPECTED.md").read_text()
    match = _re.search(r"```python\n(@server\.tool\(\).*?)```", doc, _re.S)
    assert match, "Lab 2's reference solution block is missing"

    block = match.group(1)
    tree = _ast.parse(block)          # must be syntactically valid Python

    func = next(n for n in tree.body if isinstance(n, _ast.FunctionDef))
    assert func.name == "get_rollout_history"
    assert _ast.get_docstring(func), "the reference solution has no docstring"

    docstring = _ast.get_docstring(func).lower()
    assert "returns" in docstring, "docstring does not say what it returns"
    assert "use this" in docstring, "docstring does not say when to use it"
    assert "cheap" in docstring or "cost" in docstring, "docstring does not state cost"

    server = (REPO / "mcp" / "k8s_mcp.py").read_text()
    for dependency in ("apps = client.AppsV1Api()", "def _err("):
        assert dependency in server, \
            f"the reference solution depends on {dependency!r}, which no longer exists"

    # and the exercise it answers must actually be set. Normalise whitespace:
    # the brief is a wrapped comment block, so phrases straddle line breaks.
    assert "get_rollout_history" in server, "the exercise brief is missing from k8s_mcp.py"
    flat = " ".join(server.replace("#", " ").split())
    assert "no code here to reveal" in flat, "the write-your-own brief is missing"


def test_extension_exercise_is_described_honestly():
    """The published description says attendees extend the MCP server "with a
    tool of your own". Part one is an uncomment, which is the right call for a
    live cohort but is not writing a tool. The lab has to say which is which."""
    doc = " ".join((REPO / "labs" / "lab2-live-state-agent" / "EXPECTED.md")
                   .read_text().lower().split())
    assert "deliberately not a writing exercise" in doc
    assert "part two" in doc and "no code to reveal" in doc


@pytest.mark.parametrize("script", [
    "labs/lab1-knowledge-layer/ask.py",
    "labs/lab2-live-state-agent/investigate.py",
    "labs/lab3-guardrails/remediate.py",
    "labs/lab4-evals/run_evals.py",
    "alt/langgraph/investigate.py",
])
def test_every_lab_cli_actually_parses(script):
    """`--help` must work on every entrypoint.

    This shipped broken: adding one CLI flag per filterable metadata field
    introduced a second `--provider` — the runbook frontmatter's cloud provider
    colliding with the LLM provider — and argparse raised on construction. Lab
    1, the first demo of the session, could not start.

    73 tests were green at the time. None of them invoked a parser.
    """
    import subprocess
    import sys

    interpreter = sys.executable
    if script.startswith("alt/"):
        venv = REPO / "alt" / "langgraph" / ".venv" / "bin" / "python"
        if not venv.exists():
            pytest.skip("the frozen port's venv is not installed here")
        interpreter = str(venv)

    proc = subprocess.run([interpreter, str(REPO / script), "--help"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, (
        f"{script} --help failed:\n{proc.stderr[-800:]}"
    )
    assert "usage:" in proc.stdout.lower()


def test_no_duplicate_cli_flags_within_a_lab():
    """The collision above is the general case: two features each adding a flag
    with a name that reads naturally for both."""
    import re as _re

    for script in ["labs/lab1-knowledge-layer/ask.py",
                   "labs/lab2-live-state-agent/investigate.py",
                   "labs/lab3-guardrails/remediate.py",
                   "labs/lab4-evals/run_evals.py"]:
        source = (REPO / script).read_text()
        flags = _re.findall(r'add_argument\(\s*"(--[a-z][a-z-]*)"', source)
        duplicates = {f for f in flags if flags.count(f) > 1}
        assert not duplicates, f"{script} defines {sorted(duplicates)} twice"


def test_no_two_flags_share_a_dest():
    """`--help` succeeding is not enough.

    Giving --cloud-provider `dest="provider"` builds a perfectly valid parser
    and then silently overwrites the LLM provider's default with None. The
    parser test passed; `make lab1` died with KeyError: None at call time.
    """
    import re as _re

    for script in ["labs/lab1-knowledge-layer/ask.py",
                   "labs/lab2-live-state-agent/investigate.py",
                   "labs/lab3-guardrails/remediate.py",
                   "labs/lab4-evals/run_evals.py"]:
        source = (REPO / script).read_text()
        dests = []
        for call in _re.findall(r"add_argument\((.*?)\)\n", source, _re.S):
            explicit = _re.search(r'dest\s*=\s*"([a-z_]+)"', call)
            if explicit:
                dests.append(explicit.group(1))
                continue
            flag = _re.search(r'"--([a-z][a-z-]*)"', call)
            if flag:
                dests.append(flag.group(1).replace("-", "_"))
        duplicates = {d for d in dests if dests.count(d) > 1}
        assert not duplicates, f"{script}: two arguments share dest {sorted(duplicates)}"


def test_lab1_actually_runs_both_ways():
    """The end-to-end check the parser tests could not make.

    Lab 1 needs no cluster and no API key in --retrieval-only mode, so this runs
    anywhere — including CI. It is the first demo of the session; it should be
    the most-tested path in the repo, and until now it was untested end to end.
    """
    import subprocess
    import sys

    question = "why are prod inference pods repeatedly restarting?"
    script = str(REPO / "labs" / "lab1-knowledge-layer" / "ask.py")

    filtered = subprocess.run(
        [sys.executable, script, question, "--environment", "prod",
         "--namespace", "ml-prod", "--retrieval-only"],
        capture_output=True, text=True, timeout=120)
    assert filtered.returncode == 0, filtered.stderr[-800:]
    assert "RB-014" in filtered.stdout

    unfiltered = subprocess.run(
        [sys.executable, script, question, "--no-metadata-filter", "--retrieval-only"],
        capture_output=True, text=True, timeout=120)
    assert unfiltered.returncode == 0, unfiltered.stderr[-800:]
    assert "RB-009" in unfiltered.stdout

    # The contrast is the lab. If the top hit ever agrees, there is no lesson.
    first_filtered = filtered.stdout.split("1.")[1].split()[0]
    first_unfiltered = unfiltered.stdout.split("1.")[1].split()[0]
    assert first_filtered != first_unfiltered, "the two commands returned the same runbook"


def test_every_metadata_flag_is_accepted_at_runtime():
    """Each filterable field must survive an actual invocation, not just exist
    in --help."""
    import subprocess
    import sys

    script = str(REPO / "labs" / "lab1-knowledge-layer" / "ask.py")
    for flag, value in [("--environment", "prod"), ("--cluster", "ml-cluster-1"),
                        ("--namespace", "ml-prod"), ("--service", "inference-api"),
                        ("--model", "sentiment-v2"), ("--gpu-type", "a10g"),
                        ("--cloud-provider", "aws"), ("--region", "us-east-1")]:
        proc = subprocess.run([sys.executable, script, "restarting", flag, value,
                               "--retrieval-only"],
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, f"{flag} {value} failed:\n{proc.stderr[-500:]}"


def test_tour_exists_and_orients_before_the_first_lab():
    """Every lab asks the learner to reason about ml-prod, inference-api and a
    GPU node. Until `make tour`, nothing in the repo said what any of those
    were — the README's repository layout is a file listing, not a description
    of what is deployed."""
    tour = REPO / "scripts" / "tour.sh"
    assert tour.exists() and os.access(tour, os.X_OK)

    text = tour.read_text()
    for topic in ["ml-prod", "ml-staging", "inference-api",
                  "simulated GPU pool", "RB-014", "RB-009",
                  "make reset", "MODEL_CONFIG_PATH"]:
        assert topic in text, f"the tour never mentions {topic!r}"

    assert re.search(r"^tour:", (REPO / "Makefile").read_text(), re.M), \
        "make tour is not wired up"
    assert "make tour" in (REPO / "README.md").read_text()


def test_tour_runs_without_a_cluster():
    """Tier B has no cluster and Lab 1 needs none, so the orientation they can
    actually use — the runbook corpus — must still print."""
    import subprocess

    proc = subprocess.run([str(REPO / "scripts" / "tour.sh")],
                          capture_output=True, text=True, timeout=180,
                          env={**os.environ, "KUBECONFIG": "/nonexistent"})
    assert proc.returncode == 0, proc.stderr[-600:]
    assert "RB-014" in proc.stdout and "RB-009" in proc.stdout
    assert "Lab 1 needs no cluster" in proc.stdout
