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

import json
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

    # Arguments every write tool requires. A model that gets these wrong should
    # get a message it can recover from, exactly like a failed read does.
    REQUIRED_ARGS = {
        "rollback_deployment": ("namespace", "name"),
        "scale_deployment": ("namespace", "name", "replicas"),
    }

    def handle_write(self, name: str, arguments: dict) -> str:
        namespace = arguments.get("namespace", "")

        # Validate before anything else. _preview and _execute index arguments
        # directly, so a model that says "deployment" instead of "name" raised
        # KeyError straight out of dispatch and ended the lab with a traceback
        # mid-demo. Reads have always degraded to "ERROR: ..." text; writes must
        # too.
        missing = [a for a in self.REQUIRED_ARGS.get(name, ()) if a not in arguments]
        if missing:
            msg = (f"ERROR: {name} called without required argument(s) "
                   f"{', '.join(missing)}. Required: "
                   f"{', '.join(self.REQUIRED_ARGS.get(name, ()))}.")
            self.audit.record(tool=name, arguments=arguments, result_summary=msg,
                              approval="refused_invalid_arguments")
            return msg

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

        # Refuse categorically-unsafe changes BEFORE showing a human anything.
        # This check used to live in _execute, downstream of the gate: the
        # operator was shown an approval prompt for an outage-causing change,
        # approved it, the write was then refused — and the audit line said
        # "granted". A log that records a production write as granted when it
        # never happened is worse than no log.
        if name == "scale_deployment" and int(arguments.get("replicas", 1)) < 1:
            msg = ("REFUSED: scaling to zero turns a degraded service into an "
                   "outage, and a stalled rollout is already protecting you by "
                   "keeping the previous ReplicaSet serving. Propose a rollback "
                   "instead.")
            self.audit.record(tool=name, arguments=arguments, result_summary=msg,
                              approval="refused_unsafe")
            return msg

        dry_run = bool(arguments.get("dry_run", True))
        description, diff = self._preview(name, arguments)
        if description is None:
            self.audit.record(tool=name, arguments=arguments, result_summary=diff,
                              approval="refused_preview_failed")
            return diff

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
    def _container_of(self, args: list[str]) -> dict:
        """Return the first container spec from a kubectl -o json query."""
        code, out = _kubectl(*args, "-o", "json", kubeconfig=self.kubeconfig)
        if code != 0:
            return {}
        try:
            obj = json.loads(out)
        except json.JSONDecodeError:
            return {}
        if obj.get("kind") == "List":
            return obj
        spec = obj.get("spec", {}).get("template", {}).get("spec", {})
        containers = spec.get("containers") or [{}]
        return containers[0]

    @staticmethod
    def _describe_container(c: dict) -> dict:
        """The fields a rollback can actually change, flattened for diffing."""
        fields = {"image": c.get("image", "<none>")}
        for e in c.get("env") or []:
            if e.get("value") is not None:
                fields[f"env.{e['name']}"] = e["value"]
        res = c.get("resources") or {}
        for kind in ("requests", "limits"):
            for k, v in (res.get(kind) or {}).items():
                fields[f"{kind}.{k}"] = str(v)
        return fields

    def _preview_rollback(self, ns: str, dep: str) -> tuple[str, str]:
        """Show what `rollout undo` would actually change.

        The obvious implementation compares image tags, and it is wrong in the
        most important case in this repo. break-1 changes MODEL_CONFIG_PATH, an
        environment variable, and leaves the image alone — so an image-only diff
        renders as

            - image: inference-stub:v2
            + image: inference-stub:v2

        and asks a human to approve a production change while showing them
        nothing changing. A gate that under-reports the change it is gating is
        worse than no gate, because it manufactures the appearance of review.

        So diff the whole container: image, environment, requests and limits.
        """
        container = self._container_of(["-n", ns, "get", "deploy", dep])
        if not container:
            return None, (f"ERROR: could not read deployment {ns}/{dep} to build a "
                          f"preview. Refusing to prompt for approval of a change we "
                          f"cannot describe.")
        current = self._describe_container(container)

        # Find the ReplicaSet `rollout undo` would restore: the second-highest
        # revision. Revisions are not contiguous once revisionHistoryLimit has
        # pruned, so sort rather than assume N-1 exists.
        listing = self._container_of(["-n", ns, "get", "rs", "-l", f"app={dep}"])
        revisions = []
        for item in listing.get("items", []) if isinstance(listing, dict) else []:
            rev = (item.get("metadata", {}).get("annotations", {})
                   .get("deployment.kubernetes.io/revision"))
            if rev and rev.isdigit():
                containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers") or [{}]
                revisions.append((int(rev), containers[0]))
        revisions.sort(key=lambda r: r[0])

        _, history = _kubectl("-n", ns, "rollout", "history", f"deployment/{dep}",
                              kubeconfig=self.kubeconfig)
        history_lines = history.splitlines()
        if len(history_lines) > 6:
            history = "\n".join(history_lines[:2] + ["  ..."] + history_lines[-4:])

        if len(revisions) < 2:
            return (f"Roll {ns}/{dep} back one revision.",
                    f"  deployment {ns}/{dep}\n"
                    f"  WARNING: no previous revision found in history — this "
                    f"rollback may do nothing.\n\n{history}")

        target_rev, target_container = revisions[-2]
        target = self._describe_container(target_container)

        changed = sorted(set(current) | set(target))
        lines = [f"  deployment {ns}/{dep}   (rolling back to revision {target_rev})"]
        differences = 0
        for key in changed:
            before, after = current.get(key, "<unset>"), target.get(key, "<unset>")
            if before != after:
                differences += 1
                lines.append(f"- {key}: {before}")
                lines.append(f"+ {key}: {after}")

        if differences == 0:
            # Do not render an empty diff under a confident description.
            lines.append("  NO CHANGE: revision "
                         f"{target_rev} has an identical container spec.")
            lines.append("  This rollback would not alter the running workload.")
            description = (f"Roll {ns}/{dep} back to revision {target_rev} — which has "
                           f"the SAME container spec as the current revision. This would "
                           f"not change anything about the running pods.")
        else:
            description = (f"Roll {ns}/{dep} back to revision {target_rev}, changing "
                           f"{differences} field(s) of the container spec. Pods will be "
                           f"recreated.")

        return description, "\n".join(lines) + f"\n\n{history}"

    def _preview(self, name: str, arguments: dict) -> tuple[str, str]:
        ns, dep = arguments["namespace"], arguments["name"]

        if name == "rollback_deployment":
            return self._preview_rollback(ns, dep)

        if name == "scale_deployment":
            replicas = arguments["replicas"]
            code, current = _kubectl("-n", ns, "get", "deploy", dep,
                                     "-o", "jsonpath={.spec.replicas}",
                                     kubeconfig=self.kubeconfig)
            # Never put an error string where a value belongs. _kubectl returns
            # stdout+stderr, so ignoring the exit code renders
            # "- replicas: Error from server (NotFound)..." into the approval
            # prompt and then asks a human to approve it. The gate's whole value
            # is that the human is looking at the real object.
            if code != 0 or not current.strip().isdigit():
                return None, (f"ERROR: could not read {ns}/{dep} to build a preview "
                              f"({current.strip()[:200]}). Refusing to prompt for "
                              f"approval of a change we cannot describe.")
            description = f"Change the replica count of {ns}/{dep} from {current} to {replicas}."
            diff = f"  deployment {ns}/{dep}\n- replicas: {current}\n+ replicas: {replicas}"
            return description, diff

        return f"{name}({arguments})", "<no preview available>"

    def _execute(self, name: str, arguments: dict) -> str:
        ns, dep = arguments["namespace"], arguments["name"]

        if name == "rollback_deployment":
            # Snapshot before, so we can report what actually happened rather
            # than echo kubectl. `rollout undo` prints "rolled back" even when
            # the previous revision has an identical template and nothing
            # changed, and reporting APPLIED for a no-op is how an operator ends
            # up believing an incident is resolved when it is not.
            before = self._describe_container(
                self._container_of(["-n", ns, "get", "deploy", dep]))
            code, out = _kubectl("-n", ns, "rollout", "undo", f"deployment/{dep}",
                                 kubeconfig=self.kubeconfig)
            if code == 0:
                after = self._describe_container(
                    self._container_of(["-n", ns, "get", "deploy", dep]))
                changed = {k for k in set(before) | set(after)
                           if before.get(k) != after.get(k)}
                if not changed:
                    result = (f"NO CHANGE: {out}\n"
                              f"The previous revision had an identical container spec, so "
                              f"the running workload is unchanged. Do not treat this as a "
                              f"resolved incident.")
                    self.audit.record(tool=name, arguments=arguments,
                                      result_summary=result, approval="granted")
                    return result
                detail = ", ".join(f"{k}: {before.get(k, '<unset>')} -> {after.get(k, '<unset>')}"
                                   for k in sorted(changed))
                out = f"{out} ({detail})"
        elif name == "scale_deployment":
            code, out = _kubectl("-n", ns, "scale", f"deployment/{dep}",
                                 f"--replicas={arguments['replicas']}",
                                 kubeconfig=self.kubeconfig)
        else:
            return f"ERROR: unknown write tool {name}"

        if code != 0:
            return f"ERROR applying change: {out}"
        return f"APPLIED: {out}"
