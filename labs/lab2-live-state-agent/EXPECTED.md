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

model: claude-opus-5 · tools: 13 · max 12 iterations

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

## Extending the MCP server (the exercise)

Open `mcp/k8s_mcp.py` and find `get_resource_quota`. The docstring is written;
the body is commented out. Uncomment the eight lines between the two marker
comments and re-run any scenario.

Read the docstring before you uncomment it. Notice that it does not describe
the implementation — it says what comes back, when this tool is the right call
rather than `get_nodes`, and what it costs. Node capacity and namespace quota
are two independent ceilings on scheduling, and that sentence is what will make
the model reach for this tool at the right moment.

The agent's Role already permits reading ResourceQuota, so it works as soon as
you uncomment it. No restart of anything else is needed — the MCP server is a
subprocess started fresh on each run.

---

## If it stops at 12 iterations

The cap is real and it is in `agent/loop.py`. Hitting it means the model kept
asking for tools without converging — usually because the fault was reset out
from under it, or several faults are stacked and the evidence contradicts
itself. `make reset`, inject one fault, and try again.
