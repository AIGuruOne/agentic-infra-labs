# Lab 2 — The Agent Meets the Cluster · expected output

Lab 1 retrieved a runbook. This lab retrieves a runbook and then goes and
checks the cluster against it.

You need a running cluster and an API key for this one. If you have neither,
read on — everything below is real captured output, and the reasoning is the
part worth reading anyway.

Exact wording varies between runs and between models. The **tool sequence** and
the **conclusion** are what should match.

---

## Scenario 01 — pods restarting

```
$ make break-1
$ make lab2 ARGS='--scenario 1'
```

```
runbooks retrieved (filter ON)
  RB-014  score  4.99  environment=prod  Model server crashloop after config change
  RB-013  score  2.92  environment=prod  Model server OOMKilled under batch load

model: claude-opus-5 · tools: 12 · max 12 iterations

  -> list_pods(namespace='ml-prod')
     inference-api-6744969cc9-5bxkx  phase=Running  ready=0/1  restarts=6  waiting=CrashLoopBackOff
     ... 3 healthy pods from the previous ReplicaSet ...

  -> describe_pod(namespace='ml-prod', name='inference-api-6744969cc9-5bxkx')
     env: MODEL_CONFIG_PATH=/etc/model/config-v3.json
     last terminated: reason=Error exit_code=1

  -> get_pod_logs(namespace='ml-prod', name='inference-api-...', previous=True)
     FATAL: model config not found at '/etc/model/config-v3.json'
     FATAL: sentiment-v2 cannot start without its config file.
     FATAL: check the MODEL_CONFIG_PATH env var on this deployment.

ROOT CAUSE
  MODEL_CONFIG_PATH points at /etc/model/config-v3.json, which is not present
  in the image. The server validates the path at boot and exits 1 rather than
  serving from an undefined revision. [RB-014]

REMEDIATION
  kubectl -n ml-prod rollout history deployment/inference-api
  kubectl -n ml-prod rollout undo deployment/inference-api
  kubectl -n ml-prod rollout status deployment/inference-api
  Do NOT delete the model ConfigMap in production. [RB-014]

CONFIDENCE
  High — the log line names the exact path and the env var that set it.

done in 4 iteration(s) · tools: list_pods, describe_pod, get_pod_logs
```

Three things worth pausing on:

**It called `get_pod_logs` with `previous=True`.** Nothing told it to. The tool
description explains that a CrashLoopBackOff pod's current container has no
useful logs and the error is in the previous instance. That sentence in a
docstring is worth more than any amount of implementation quality — it is the
only thing the model knows about the tool at the moment it chooses.

**It called `describe_pod` on one pod, not four.** `list_pods` gave it the
restart counts, so it knew which pod mattered before spending tokens.

**Three tool calls, not twelve.** The loop stops when the model stops asking
for tools. It is not a fixed pipeline.

---

## Scenario 02 — GPU scheduling

```
$ make reset && make break-2
$ make lab2 ARGS='--scenario 2'
```

```
  -> list_pods(namespace='ml-prod')
     embedding-trainer-fdc5b4689-wf2m8  phase=Pending  ready=0/0  node=<unscheduled>

  -> get_events(namespace='ml-prod')
     Warning  FailedScheduling  Pod/embedding-trainer-...: 0/3 nodes are available:
     1 Insufficient nvidia.com/gpu, 2 node(s) had untolerated taint(s).

  -> get_nodes()
     agentic-infra-labs-worker2  instance-type=g5.xlarge  nvidia.com/gpu=2
         taints: nvidia.com/gpu=present:NoSchedule

ROOT CAUSE
  Two independent causes, both present:
  1. The pod requests 4 GPUs. The only GPU node advertises 2, and GPU requests
     cannot be split across nodes.
  2. The pod has no toleration for nvidia.com/gpu=present:NoSchedule, so it is
     refused by that node regardless of capacity. [RB-002]

REMEDIATION
  Reduce the request to <= 2 AND add the matching toleration. Fixing only one
  leaves the pod Pending.

done in 3 iteration(s) · tools: list_pods, get_events, get_nodes
```

**This is the scenario that justifies the whole architecture.** Fixing one
cause and re-checking looks like the fix did nothing. The scheduler stated both
reasons in a single event; the agent read the whole message rather than the
first clause, and the tool description for `get_events` is what told it to.

A retrieval-only chatbot cannot do this. RB-002 describes both failure modes in
general, but only the live event says which ones are true here, and only
`get_nodes` says the number is 2 rather than 8.

---

## Extending the MCP server — the exercise, in two parts

The session description says you will extend the Kubernetes MCP server "with a
tool of your own". Being precise about what that means, because the two halves
are different exercises:

### Part one — uncomment (about 5 minutes)

Open `mcp/k8s_mcp.py` and find the commented block for `get_resource_quota`.
The decorator, the docstring and the body are all written; uncomment them and
re-run any scenario.

**This is deliberately not a writing exercise.** A blank function in front of a
global cohort is a dead ten minutes, and the thing worth your attention here is
not the eight lines of implementation.

Read the docstring before you uncomment it. Notice that it does not describe the
code. It says what comes back, when this tool is the right call *rather than*
`get_nodes`, and what it costs:

> *"Use this when a workload will not schedule and the nodes look like they have
> room. Node capacity and namespace quota are two independent ceilings: a pod
> can be rejected because the namespace has exhausted its quota even though the
> cluster has plenty of free CPU."*

That sentence is what makes the model reach for it at the right moment. The
implementation underneath is the easy half.

Note also that the decorator is commented out, not just the body. A tool that is
registered but returns "not implemented" is still advertised to the model, which
will call it, read the apology, and have spent an iteration and a few thousand
tokens learning nothing.

### Part two — write one (about 20 minutes)

This one is yours, and there is no code to reveal.

**The gap:** nothing in this server exposes a Deployment's *rollout history*.
The agent can see what is running now and it can read events, but it cannot see
which revision introduced a change, or what the previous revision looked like.
That is the single most useful missing fact in scenarios 01 and 07 — the two
whose remediation is `rollout undo`.

**Write `get_rollout_history(namespace, name)`.** ReplicaSets carry the revision
number in the annotation `deployment.kubernetes.io/revision`, and the agent's
Role already permits reading them, so no RBAC change is needed.

**Write the docstring first.** Make it answer the same three questions every
other tool in that file answers — what it returns, when to use it rather than
`get_deployment`, and what it costs. Then run scenario 01 and watch whether the
model calls it *unprompted*.

If it does not, the docstring is the thing to change, not the code. That is the
whole lesson of Segment 2, and this is where you get to test it on something you
wrote.

---

## Reference solution — try part two before reading this

Roughly twenty lines. Yours will differ, and the interesting variation is in the
docstring rather than the body.

```python
@server.tool()
def get_rollout_history(namespace: str, name: str) -> str:
    """Revision history for a Deployment: what each revision was running.

    Returns one row per revision, newest first — revision number, current
    replica count, container image, and the MODEL_CONFIG_PATH it was deployed
    with. The row with a non-zero replica count is the revision serving now.

    Use this when something changed and you need to know WHAT changed.
    get_deployment tells you the current spec; this tells you the spec before
    it, which is what turns "the config path is wrong" into "revision 32
    introduced the wrong config path, and revision 31 was fine". It is also how
    you confirm a rollback has somewhere safe to land before proposing one.

    Cheap — one API call. Truncated to the six most recent revisions.
    """
    try:
        replica_sets = apps.list_namespaced_replica_set(
            namespace, label_selector=f"app={name}")
    except Exception as e:
        return _err(e)

    rows = []
    for rs in replica_sets.items:
        revision = (rs.metadata.annotations or {}).get(
            "deployment.kubernetes.io/revision")
        if not revision or not revision.isdigit():
            continue
        container = rs.spec.template.spec.containers[0]
        env = {e.name: e.value for e in (container.env or []) if e.value is not None}
        rows.append((int(revision), rs.spec.replicas, container.image,
                     env.get("MODEL_CONFIG_PATH", "-")))

    if not rows:
        return f"no rollout history for {namespace}/{name}"

    rows.sort(reverse=True)
    out = ["revision  replicas  image                          MODEL_CONFIG_PATH"]
    for revision, replicas, image, config_path in rows[:6]:
        marker = "  <- serving now" if replicas else ""
        out.append(f"{revision:>8}  {replicas:>8}  {image:<30} {config_path}{marker}")
    return "\n".join(out)
```

Real output, immediately after `make break-1`:

```
revision  replicas  image                          MODEL_CONFIG_PATH
      33         3  inference-stub:v2              /etc/model/config.json  <- serving now
      32         0  inference-stub:v2              /etc/model/config-v3.json
      28         0  inference-stub:v3-broken       /etc/model/config.json
```

Revision 32 is the one that broke it, and the image never changed — which is
exactly the fact scenario 01's diagnosis has to establish, and which the agent
currently has to infer from a pod spec instead of reading directly.

---

## If it stops at 12 iterations

The cap is real and it is in `agent/loop.py`. Hitting it means the model kept
asking for tools without converging — usually because the fault was reset out
from under it, or several faults are stacked and the evidence contradicts
itself. `make reset`, inject one fault, and try again.
