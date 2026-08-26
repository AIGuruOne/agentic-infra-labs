#!/usr/bin/env python3
"""k8s-mcp — read-only Kubernetes tools for the infrastructure agent.

Every tool here is read-only. Writes live in agent/guardrails.py and are gated;
nothing in this file can change cluster state.

## On writing tool descriptions

The docstrings below are not documentation. They are the prompt — the only
thing the model knows about these tools at the moment it decides which to call.
Every one of them answers three questions:

  what it returns   so the model can tell whether this is the right tool
  when to use it    so it picks between overlapping tools correctly
  what it costs     so it does not call get_pod_logs on 40 pods to find one

Written the way you would brief a junior engineer joining the on-call rotation.
A vague description here costs far more tokens and far more wrong turns than a
slow implementation ever will.

## Credentials

Connects with cluster/rbac/agent.kubeconfig — the scoped `infra-agent`
ServiceAccount, not your admin context. A read outside ml-prod/ml-staging fails
with a 403 from the API server, not from a check in this file. That is
deliberate: a guardrail the agent could talk its way past is not a guardrail.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

from kubernetes import client, config
from mcp.server import MCPServer

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_KUBECONFIG = REPO_ROOT / "cluster" / "rbac" / "agent.kubeconfig"

server = MCPServer(
    name="k8s-mcp",
    instructions=(
        "Read-only access to the live Kubernetes cluster. Use these tools to "
        "establish what is actually true right now, rather than what "
        "documentation says should be true. Prefer list_* to narrow down, then "
        "describe_pod or get_pod_logs on the specific pod you care about."
    ),
)


CONFIG_ERROR = ""


def _load() -> None:
    """Load credentials, or record why we could not.

    This runs at import. Raising here kills the MCP subprocess during startup,
    and the caller sees an opaque MCP handshake failure rather than "run
    `make cluster` first" — which is exactly the situation a Tier B attendee or
    a fresh CI runner is in, since neither has a kubeconfig at all.

    So: record the problem and let every tool report it as text. An agent can
    reason about "no cluster credentials"; it cannot reason about a dead pipe.
    """
    global CONFIG_ERROR
    kubeconfig = os.environ.get("AGENT_KUBECONFIG", str(AGENT_KUBECONFIG))
    try:
        if Path(kubeconfig).exists():
            config.load_kube_config(config_file=kubeconfig)
        else:
            # Ambient context, so the tools work before `make cluster` has
            # generated the scoped kubeconfig. Lab 3's RBAC demo needs the
            # scoped one; everything else works either way.
            config.load_kube_config()
    except Exception as e:
        CONFIG_ERROR = (
            f"no usable Kubernetes credentials ({type(e).__name__}: {e}). "
            "Run `make cluster` first, or set AGENT_KUBECONFIG."
        )


_load()
core = client.CoreV1Api()
apps = client.AppsV1Api()
autoscaling = client.AutoscalingV2Api()


def _clean_logs(logs) -> str:
    """Return pod logs as readable text.

    kubernetes==36.0.3 hands back a *str containing the repr of bytes* —
    literally `'b"FATAL: ...\\n..."'` — not a bytes object and not the text.
    An isinstance(bytes) check cannot catch that, so it has to be unwrapped.

    Left unwrapped, the model reads escaped \\n instead of line breaks. It can
    still usually parse a three-line error that way; a fifty-line Java stack
    trace on one physical line is a different matter.
    """
    if isinstance(logs, bytes):
        return logs.decode("utf-8", errors="replace") or "<no output>"
    if isinstance(logs, str) and len(logs) > 2 and logs[0] == "b" and logs[1] in "\"'":
        try:
            decoded = ast.literal_eval(logs)
            if isinstance(decoded, bytes):
                return decoded.decode("utf-8", errors="replace") or "<no output>"
        except (ValueError, SyntaxError):
            pass
    return logs or "<no output>"


def _no_cluster() -> str:
    return f"ERROR: {CONFIG_ERROR}"


def _err(e: Exception) -> str:
    """Return API errors as text rather than raising.

    A 403 is information the agent needs to reason about ("I am not permitted
    to read that namespace"), not a crash. Raising here would end the loop on
    exactly the moment Lab 3 is built to demonstrate.
    """
    if isinstance(e, client.ApiException):
        return f"ERROR {e.status} {e.reason}: {json.loads(e.body).get('message', '')[:400]}" \
            if e.body else f"ERROR {e.status} {e.reason}"
    return f"ERROR: {e}"


# Namespaces the agent is scoped to. Used only as the fallback when a
# cluster-wide list is refused.
SCOPED_NAMESPACES = ("ml-prod", "ml-staging")


def _services_everywhere_visible():
    """List Services across every namespace the caller can actually reach.

    A cluster-wide list is the natural implementation and it is forbidden for
    the agent's ServiceAccount, whose Role is namespaced to ml-prod and
    ml-staging by design. Widening the Role to fix this would trade the entire
    blast-radius story for one convenience.

    So: try cluster-wide, because the repo also supports running these tools
    with your own broader credentials, and fall back to the scoped namespaces on
    403. The return carries a note saying which path was taken — an agent that
    is silently seeing less than it asked for will conclude "there is no such
    service elsewhere" when the truth is "I was not allowed to look".
    """
    try:
        return core.list_service_for_all_namespaces().items, ""
    except client.ApiException as e:
        if e.status != 403:
            return _err(e), ""

    items = []
    for ns in SCOPED_NAMESPACES:
        try:
            items.extend(core.list_namespaced_service(ns).items)
        except Exception:
            continue
    note = ("searched only " + ", ".join(SCOPED_NAMESPACES) +
            " — this ServiceAccount is not permitted to list Services "
            "cluster-wide, so other namespaces were not examined")
    return items, note


@server.tool()
def list_pods(namespace: str, label_selector: str = "") -> str:
    """List pods in a namespace with their phase, readiness, and restart count.

    Returns one line per pod: name, phase, ready containers, restart count, node,
    and the container's current waiting reason if it has one (CrashLoopBackOff,
    ImagePullBackOff, etc.).

    Use this first for almost any incident. The restart count and waiting reason
    together usually tell you which single pod to investigate, so you can call
    the expensive tools once instead of nine times.

    Cheap — one API call regardless of pod count.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        pods = core.list_namespaced_pod(namespace, label_selector=label_selector or None)
    except Exception as e:
        return _err(e)
    if not pods.items:
        return f"no pods in {namespace}" + (f" matching {label_selector}" if label_selector else "")

    lines = []
    for p in pods.items:
        statuses = p.status.container_statuses or []
        ready = sum(1 for c in statuses if c.ready)
        restarts = sum(c.restart_count for c in statuses)
        waiting = next(
            (c.state.waiting.reason for c in statuses if c.state and c.state.waiting and c.state.waiting.reason),
            "",
        )
        lines.append(
            f"{p.metadata.name}  phase={p.status.phase}  ready={ready}/{len(statuses)}  "
            f"restarts={restarts}  node={p.spec.node_name or '<unscheduled>'}"
            + (f"  waiting={waiting}" if waiting else "")
        )
    return "\n".join(lines)


@server.tool()
def describe_pod(namespace: str, name: str) -> str:
    """Full detail for one pod: containers, images, env vars, resource requests
    and limits, tolerations, volume mounts, container states including the last
    termination reason and exit code, and the pod's conditions.

    Use this when list_pods has told you which pod is unhealthy and you need to
    know why. The env vars and the last-termination reason are usually where the
    answer is for a crashloop; the tolerations and resource requests are where
    it is for a Pending pod.

    Moderately expensive — this is a lot of text. Call it on one pod, not on
    every pod in a namespace.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        p = core.read_namespaced_pod(name, namespace)
    except Exception as e:
        return _err(e)

    out = [f"pod {namespace}/{p.metadata.name}",
           f"phase: {p.status.phase}",
           f"node: {p.spec.node_name or '<unscheduled>'}"]

    if p.spec.tolerations:
        out.append("tolerations: " + ", ".join(
            f"{t.key}={t.value}:{t.effect}" for t in p.spec.tolerations if t.key))

    for c in p.spec.containers:
        out.append(f"\ncontainer {c.name}")
        out.append(f"  image: {c.image}")
        if c.env:
            out.append("  env:")
            out += [f"    {e.name}={e.value}" for e in c.env if e.value is not None]
        if c.resources:
            if c.resources.requests:
                out.append(f"  requests: {dict(c.resources.requests)}")
            if c.resources.limits:
                out.append(f"  limits: {dict(c.resources.limits)}")

    for cs in p.status.container_statuses or []:
        out.append(f"\nstatus {cs.name}: ready={cs.ready} restarts={cs.restart_count}")
        if cs.state and cs.state.waiting:
            out.append(f"  waiting: {cs.state.waiting.reason} — {cs.state.waiting.message or ''}")
        if cs.last_state and cs.last_state.terminated:
            t = cs.last_state.terminated
            out.append(f"  last terminated: reason={t.reason} exit_code={t.exit_code}")

    for cond in p.status.conditions or []:
        if cond.status != "True":
            out.append(f"condition {cond.type}=False: {cond.reason} {cond.message or ''}")
    return "\n".join(out)


@server.tool()
def get_pod_logs(namespace: str, name: str, container: str = "", tail_lines: int = 50,
                 previous: bool = False) -> str:
    """Container logs for one pod, most recent `tail_lines` lines.

    Set previous=True to read the logs of the *last terminated* container. For a
    pod in CrashLoopBackOff this is almost always what you want — the current
    container is either not running or has only just started, so its logs are
    empty and the error you need is in the previous instance.

    Expensive in tokens, proportional to tail_lines. Start at 50. Only raise it
    if the failure is genuinely not in the last 50 lines.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        logs = core.read_namespaced_pod_log(
            name, namespace, container=container or None,
            tail_lines=tail_lines, previous=previous,
        )
    except Exception as e:
        return _err(e)
    return _clean_logs(logs)


@server.tool()
def get_events(namespace: str, limit: int = 20) -> str:
    """Recent events in a namespace, oldest first, with type, reason, object and
    message.

    This is the single highest-value tool for anything that will not schedule or
    will not start. The scheduler writes its reasoning here in full — a
    FailedScheduling event names *every* reason a pod could not be placed, not
    just the first one. Read the whole message before concluding.

    Cheap. Worth calling early on any Pending or BackOff symptom.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        events = core.list_namespaced_event(namespace)
    except Exception as e:
        return _err(e)
    items = sorted(events.items, key=lambda e: e.last_timestamp or e.event_time or "")
    items = items[-limit:]
    if not items:
        return f"no recent events in {namespace}"
    return "\n".join(
        f"{e.type:<8} {e.reason:<22} {e.involved_object.kind}/{e.involved_object.name}: "
        f"{(e.message or '').strip()}"
        for e in items
    )


@server.tool()
def list_deployments(namespace: str) -> str:
    """List Deployments in a namespace with replica counts and images.

    Returns name, ready/desired replicas, up-to-date and available counts, and
    the container image of each.

    Use this to see whether a rollout is complete or stalled: ready < desired
    with the old ReplicaSet still available means a rollout is stuck partway,
    which is a different incident from "everything is down".

    Cheap.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        deps = apps.list_namespaced_deployment(namespace)
    except Exception as e:
        return _err(e)
    if not deps.items:
        return f"no deployments in {namespace}"
    return "\n".join(
        f"{d.metadata.name}  ready={d.status.ready_replicas or 0}/{d.spec.replicas}  "
        f"updated={d.status.updated_replicas or 0}  available={d.status.available_replicas or 0}  "
        f"image={d.spec.template.spec.containers[0].image}"
        for d in deps.items
    )


@server.tool()
def get_deployment(namespace: str, name: str) -> str:
    """Full spec and status for one Deployment: image, replicas, strategy, env
    vars, resource requests and limits, and its rollout conditions.

    Use this to compare the same service across two namespaces — call it twice
    and diff the output. That is the correct way to answer "how does prod differ
    from staging", because it reads what is actually deployed rather than what a
    document claims.

    Moderate cost.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        d = apps.read_namespaced_deployment(name, namespace)
    except Exception as e:
        return _err(e)
    c = d.spec.template.spec.containers[0]
    out = [
        f"deployment {namespace}/{d.metadata.name}",
        f"replicas: desired={d.spec.replicas} ready={d.status.ready_replicas or 0} "
        f"available={d.status.available_replicas or 0}",
        f"strategy: {d.spec.strategy.type}",
        f"image: {c.image}",
        f"generation: {d.metadata.generation} observed={d.status.observed_generation}",
    ]
    if c.env:
        out.append("env:")
        out += [f"  {e.name}={e.value}" for e in c.env if e.value is not None]
    if c.resources:
        if c.resources.requests:
            out.append(f"requests: {dict(c.resources.requests)}")
        if c.resources.limits:
            out.append(f"limits: {dict(c.resources.limits)}")
    for cond in d.status.conditions or []:
        out.append(f"condition {cond.type}={cond.status}: {cond.reason} — {(cond.message or '')[:200]}")
    return "\n".join(out)


@server.tool()
def list_services(namespace: str = "") -> str:
    """List Services, in one namespace or across every namespace you can see.

    Returns namespace, name, type, cluster IP, ports, selector, and any
    `description` annotation.

    Omit the namespace when you need to find where a service actually lives.
    Be careful with the results: a Service's *name* and its annotations are
    written by humans and are not authoritative. A Service called
    "inference-api-prod" living in ml-staging is a naming convention, not a
    fact. Follow the selector to real pods before concluding anything.

    Cheap.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    if namespace:
        try:
            items = core.list_namespaced_service(namespace).items
        except Exception as e:
            return _err(e)
    else:
        items, scope_note = _services_everywhere_visible()
        if isinstance(items, str):
            return items

    lines = []
    for s in items:
        if s.metadata.namespace in ("kube-system", "kube-public", "kube-node-lease", "local-path-storage"):
            continue
        ports = ",".join(f"{p.port}->{p.target_port}" for p in (s.spec.ports or []))
        desc = (s.metadata.annotations or {}).get("description", "")
        lines.append(
            f"{s.metadata.namespace}/{s.metadata.name}  type={s.spec.type}  ports={ports}  "
            f"selector={s.spec.selector}" + (f'  annotation="{desc}"' if desc else "")
        )
    out = "\n".join(lines) or "no services found"
    if not namespace and scope_note:
        out += f"\n\n({scope_note})"
    return out


@server.tool()
def get_hpa(namespace: str, name: str = "") -> str:
    """HorizontalPodAutoscaler spec and live status.

    Returns minReplicas, maxReplicas, current replicas, the target metric and
    threshold, and the *current measured value* of that metric.

    Read all of these together before judging whether autoscaling works. An HPA
    can be present and correctly reconciling and still be incapable of ever
    scaling: a threshold above what the workload ever reaches, minReplicas equal
    to maxReplicas, or a current value of <unknown> because no metrics source is
    running. Each of those is sufficient on its own.

    Cheap.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        hpas = ([autoscaling.read_namespaced_horizontal_pod_autoscaler(name, namespace)]
                if name else
                autoscaling.list_namespaced_horizontal_pod_autoscaler(namespace).items)
    except Exception as e:
        return _err(e)
    if not hpas:
        return f"no HorizontalPodAutoscaler in {namespace}"

    out = []
    for h in hpas:
        out.append(f"hpa {namespace}/{h.metadata.name} -> {h.spec.scale_target_ref.kind}/{h.spec.scale_target_ref.name}")
        out.append(f"  minReplicas={h.spec.min_replicas} maxReplicas={h.spec.max_replicas} "
                   f"currentReplicas={h.status.current_replicas} desiredReplicas={h.status.desired_replicas}")
        for m in h.spec.metrics or []:
            if m.resource:
                out.append(f"  target: {m.resource.name} utilization {m.resource.target.average_utilization}%")
        for m in h.status.current_metrics or []:
            if m.resource:
                cur = m.resource.current.average_utilization
                out.append(f"  current: {m.resource.name} utilization "
                           f"{cur if cur is not None else '<unknown>'}%")
        for c in h.status.conditions or []:
            out.append(f"  condition {c.type}={c.status}: {c.reason} — {(c.message or '')[:160]}")
    return "\n".join(out)


@server.tool()
def get_nodes() -> str:
    """List cluster nodes with instance type labels, allocatable CPU, memory and
    GPU, taints, and Ready status.

    Use this for any scheduling question. A Pending pod is a conversation
    between what the pod asks for and what the nodes offer, and you cannot have
    that conversation with only one side of it. Check both the allocatable GPU
    count and the taints — they are independent reasons a pod may not schedule
    and they frequently occur together.

    Cheap. This is a cluster-scoped read and is the only one the agent's
    credentials permit.
    """
    if CONFIG_ERROR:
        return _no_cluster()
    try:
        nodes = core.list_node()
    except Exception as e:
        return _err(e)
    out = []
    for n in nodes.items:
        alloc = n.status.allocatable or {}
        labels = n.metadata.labels or {}
        ready = next((c.status for c in n.status.conditions or [] if c.type == "Ready"), "?")
        taints = ", ".join(f"{t.key}={t.value}:{t.effect}" for t in (n.spec.taints or [])) or "none"
        out.append(
            f"{n.metadata.name}  ready={ready}  "
            f"instance-type={labels.get('node.kubernetes.io/instance-type', '-')}  "
            f"cpu={alloc.get('cpu')}  memory={alloc.get('memory')}  "
            f"nvidia.com/gpu={alloc.get('nvidia.com/gpu', '0')}\n"
            f"    taints: {taints}"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Lab 2 extension exercise
# ---------------------------------------------------------------------------
# Uncomment the block below — the decorator, the def, and the body — to give the
# agent a new tool.
#
# Read the docstring first, and notice what it is doing: it says what comes
# back, when reaching for this tool is the right call rather than get_nodes, and
# roughly what it costs. That framing is most of what makes a tool usable by a
# model. The implementation underneath is the easy half.
#
# The decorator is commented out too, deliberately. A tool that is registered
# but returns "not implemented" is still advertised to the model, which will
# call it, read the apology, and have spent an iteration and a few thousand
# tokens learning nothing. An unregistered tool costs nothing.
#
# The ResourceQuota read is already permitted by the agent's Role, so this works
# as soon as you uncomment it and re-run the lab.
#
# @server.tool()
# def get_resource_quota(namespace: str) -> str:
#     """ResourceQuota limits and current usage for a namespace.
#
#     Returns each quota's hard limits alongside what is currently consumed —
#     CPU, memory, pod count, and any extended resources such as nvidia.com/gpu.
#
#     Use this when a workload will not schedule and the *nodes* look like they
#     have room. Node capacity and namespace quota are two independent ceilings:
#     a pod can be rejected because the namespace has exhausted its quota even
#     though the cluster has plenty of free CPU. get_nodes answers the first
#     question; this answers the second.
#
#     Cheap — one API call.
#     """
#     if CONFIG_ERROR:
#         return _no_cluster()
#     try:
#         quotas = core.list_namespaced_resource_quota(namespace)
#     except Exception as e:
#         return _err(e)
#     if not quotas.items:
#         return f"no ResourceQuota set in {namespace} — usage is bounded only by node capacity"
#     return "\n".join(
#         f"{q.metadata.name}\n  hard: {dict(q.status.hard or {})}\n  used: {dict(q.status.used or {})}"
#         for q in quotas.items
#     )


# ---------------------------------------------------------------------------
# Lab 2 extension exercise, part two — write one yourself
# ---------------------------------------------------------------------------
# Part one above is an uncomment. This one is not: there is no code here to
# reveal, because the point is that you write the description as well as the
# body.
#
# The gap: nothing in this server exposes a Deployment's *rollout history*. The
# agent can see what is running now, and it can read events, but it cannot see
# which revision introduced a change or what the previous revision looked like.
# That is the single most useful missing fact in scenarios 01 and 07 — the ones
# whose remediation is `rollout undo`.
#
# Write `get_rollout_history(namespace, name)`. ReplicaSets carry the revision
# number in the annotation `deployment.kubernetes.io/revision`, and the agent's
# Role already permits reading them, so nothing else has to change.
#
# Write the docstring FIRST, and make it answer the three questions every other
# tool in this file answers:
#
#     what it returns   so the model can tell this is the right tool
#     when to use it    so it reaches for this rather than get_deployment
#     what it costs
#
# Then run scenario 01 and watch whether the model calls it unprompted. If it
# does not, the docstring is the thing to change — not the code.
#
# A worked solution is at the bottom of labs/lab2-live-state-agent/EXPECTED.md.
# Try it before you read it; the interesting part is the docstring, and there is
# more than one good answer.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    server.run(transport="stdio")
