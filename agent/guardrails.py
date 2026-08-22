"""Guardrails for an agent that can act.

Four independent layers, because any one of them alone is a single point of
failure:

  1. Read-only by default    — write tools are not even offered unless the
                               session was started with --allow-writes
  2. Dry run first           — every write supports dry_run and the agent is
                               instructed to use it before proposing anything
  3. Human approval          — the actual change, printed in full, blocking on
                               a literal `y`
  4. Scoped credentials      — the API server refuses what the ServiceAccount
                               is not permitted to do, regardless of anything
                               above

Layer 4 is the one that holds when the others fail. Layers 1-3 all live in this
process and are, in principle, things a sufficiently confused agent could be
argued around. RBAC is enforced somewhere the agent cannot reach.

There is deliberately no bypass flag. Not `--yes`, not `--force`, not an
environment variable. A gate with a documented bypass is a gate that will be
bypassed in the exact circumstances it exists for — a noisy incident, at 3am,
by someone who has approved forty of these already.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from agent.audit import AuditLog

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"

CONTEXT = "kind-agentic-infra-labs"

# Writes are confined to these namespaces in this process, and independently by
# the infra-agent Role in the cluster. Two locks, one key each.
WRITABLE_NAMESPACES = {"ml-prod"}


class ApprovalRequired(Exception):
    """Raised when a write reaches the gate. Carries everything a human needs
    to decide, so the prompt is never 'allow this? y/n' with no object."""

    def __init__(self, tool: str, arguments: dict, description: str, diff: str):
        super().__init__(description)
        self.tool = tool
        self.arguments = arguments
        self.description = description
        self.diff = diff


@dataclass
class WriteTool:
    name: str
    description: str
    input_schema: dict


# ---------------------------------------------------------------------------
# Tool definitions. These are the prompt, same as the MCP docstrings.
# ---------------------------------------------------------------------------

WRITE_TOOLS = [
    WriteTool(
        name="rollback_deployment",
        description=(
            "Roll a Deployment back to its previous revision.\n\n"
            "ALWAYS call this with dry_run=true first and show the result before "
            "proposing the real change. The dry run reports which revision would "
            "be restored and what image it carries, without changing anything.\n\n"
            "Use this when a rollout has shipped a broken revision and a known-good "
            "previous revision exists in the Deployment's history. Do not use it to "
            "'clear' a stuck rollout — a stalled rollout is still serving traffic "
            "from the old ReplicaSet, and rolling back is a change to production, "
            "not a reset.\n\n"
            "Requires human approval. Scoped to the ml-prod namespace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "namespace": {"type": "string", "description": "must be ml-prod"},
                "name": {"type": "string", "description": "Deployment name"},
                "dry_run": {"type": "boolean", "description": "true = show only, change nothing"},
            },
            "required": ["namespace", "name", "dry_run"],
        },
    ),
    WriteTool(
        name="scale_deployment",
        description=(
            "Set a Deployment's replica count.\n\n"
            "Call with dry_run=true first. Scaling to zero is refused outright: it "
            "converts a degraded service into an outage and is almost never the "
            "correct response to a failing rollout.\n\n"
            "Requires human approval. Scoped to the ml-prod namespace."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "name": {"type": "string"},
                "replicas": {"type": "integer", "minimum": 1},
                "dry_run": {"type": "boolean"},
            },
            "required": ["namespace", "name", "replicas", "dry_run"],
        },
    ),
]


def tool_definitions() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.input_schema}
        for t in WRITE_TOOLS
    ]


WRITE_TOOL_NAMES = {t.name for t in WRITE_TOOLS}


def _kubectl(*args: str, kubeconfig: str | None = None) -> tuple[int, str]:
    cmd = ["kubectl"]
    if kubeconfig:
        cmd += ["--kubeconfig", kubeconfig]
    else:
        cmd += ["--context", CONTEXT]
    proc = subprocess.run(cmd + list(args), capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


class Guardrails:
    """Wraps tool dispatch. Reads pass through; writes go through the gate."""

    def __init__(self, *, allow_writes: bool, kubeconfig: str | None = None,
                 auto_approve_for_tests: bool = False):
        self.allow_writes = allow_writes
        self.kubeconfig = kubeconfig
        self.audit = AuditLog()
        # Set ONLY by the eval harness, which runs unattended and must not
        # block on stdin. It is not reachable from the CLI, deliberately.
        self._auto_approve = auto_approve_for_tests

    # -- the dispatcher handed to agent.loop -------------------------------
    async def dispatch(self, name: str, arguments: dict, registry) -> str:
        if name not in WRITE_TOOL_NAMES:
            output = await registry.call(name, arguments)
            self.audit.record(tool=name, arguments=arguments, result_summary=output)
            return output
        return self.handle_write(name, arguments)

    def handle_write(self, name: str, arguments: dict) -> str:
        namespace = arguments.get("namespace", "")

        # Layer 1 — read-only default.
        if not self.allow_writes:
            msg = (
                f"REFUSED: {name} is a write tool and this session is read-only. "
                "Propose the change and the human will decide whether to re-run "
                "with --allow-writes. Do not retry."
            )
            self.audit.record(tool=name, arguments=arguments, result_summary=msg,
                              approval="refused_read_only")
            return msg

        if namespace not in WRITABLE_NAMESPACES:
            msg = f"REFUSED: writes are scoped to {sorted(WRITABLE_NAMESPACES)}, not {namespace!r}."
            self.audit.record(tool=name, arguments=arguments, result_summary=msg,
                              approval="refused_out_of_scope")
            return msg

        dry_run = bool(arguments.get("dry_run", True))
        description, diff = self._preview(name, arguments)

        # Layer 2 — a dry run is not a write. It never reaches the gate.
        if dry_run:
            output = f"DRY RUN — nothing was changed.\n{description}\n\n{diff}"
            self.audit.record(tool=name, arguments=arguments, result_summary=output,
                              approval="not_required", dry_run=True)
            return output

        # Layer 3 — human approval.
        if not self._approve(name, arguments, description, diff):
            msg = "DENIED by human operator. The change was not applied."
            self.audit.record(tool=name, arguments=arguments, result_summary=msg,
                              approval="denied")
            return msg

        output = self._execute(name, arguments)
        self.audit.record(tool=name, arguments=arguments, result_summary=output,
                          approval="granted")
        return output

    # -- gate ---------------------------------------------------------------
    def _approve(self, name: str, arguments: dict, description: str, diff: str) -> bool:
        if self._auto_approve:
            return True

        print(f"\n{RED}{BOLD}{'=' * 68}{RESET}")
        print(f"{RED}{BOLD}  APPROVAL REQUIRED{RESET}")
        print(f"{RED}{BOLD}{'=' * 68}{RESET}")
        print(f"\n  {BOLD}tool{RESET}      {name}")
        print(f"  {BOLD}arguments{RESET} {arguments}")
        print(f"\n  {BOLD}what this will do{RESET}\n    {description}")
        print(f"\n  {BOLD}change{RESET}")
        for line in diff.splitlines():
            colour = GREEN if line.startswith("+") else RED if line.startswith("-") else DIM
            print(f"    {colour}{line}{RESET}")
        print(f"\n{RED}{BOLD}{'=' * 68}{RESET}")
        try:
            answer = input(f"{BOLD}Apply this change to production? Type 'y' to proceed: {RESET}")
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        # Exactly 'y'. Not 'yes', not 'Y', not empty. Anything else aborts, so
        # a stray newline can never approve a production write.
        return answer == "y"

    # -- preview / execute ---------------------------------------------------
    def _preview(self, name: str, arguments: dict) -> tuple[str, str]:
        ns, dep = arguments["namespace"], arguments["name"]

        if name == "rollback_deployment":
            _, current = _kubectl("-n", ns, "get", "deploy", dep,
                                  "-o", "jsonpath={.spec.template.spec.containers[0].image}",
                                  kubeconfig=self.kubeconfig)
            _, history = _kubectl("-n", ns, "rollout", "history", f"deployment/{dep}",
                                  kubeconfig=self.kubeconfig)
            _, previous = _kubectl(
                "-n", ns, "get", "rs", "-l", f"app={dep}",
                "-o", "jsonpath={range .items[*]}{.metadata.annotations.deployment\\.kubernetes\\.io/revision} "
                      "{.spec.template.spec.containers[0].image}{\"\\n\"}{end}",
                kubeconfig=self.kubeconfig)
            revisions = [l.split() for l in previous.splitlines() if l.strip()]
            revisions.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 0)
            target = revisions[-2][1] if len(revisions) >= 2 else "<unknown>"
            description = (f"Roll {ns}/{dep} back one revision, replacing the current "
                           f"image with the previous one. Pods will be recreated.")
            diff = (f"  deployment {ns}/{dep}\n"
                    f"- image: {current}\n"
                    f"+ image: {target}\n\n{history}")
            return description, diff

        if name == "scale_deployment":
            replicas = arguments["replicas"]
            _, current = _kubectl("-n", ns, "get", "deploy", dep,
                                  "-o", "jsonpath={.spec.replicas}", kubeconfig=self.kubeconfig)
            description = f"Change the replica count of {ns}/{dep} from {current} to {replicas}."
            diff = f"  deployment {ns}/{dep}\n- replicas: {current}\n+ replicas: {replicas}"
            return description, diff

        return f"{name}({arguments})", "<no preview available>"

    def _execute(self, name: str, arguments: dict) -> str:
        ns, dep = arguments["namespace"], arguments["name"]

        if name == "rollback_deployment":
            code, out = _kubectl("-n", ns, "rollout", "undo", f"deployment/{dep}",
                                 kubeconfig=self.kubeconfig)
        elif name == "scale_deployment":
            if int(arguments["replicas"]) < 1:
                return "REFUSED: scaling to zero turns a degraded service into an outage."
            code, out = _kubectl("-n", ns, "scale", f"deployment/{dep}",
                                 f"--replicas={arguments['replicas']}",
                                 kubeconfig=self.kubeconfig)
        else:
            return f"ERROR: unknown write tool {name}"

        if code != 0:
            return f"ERROR applying change: {out}"
        return f"APPLIED: {out}"
