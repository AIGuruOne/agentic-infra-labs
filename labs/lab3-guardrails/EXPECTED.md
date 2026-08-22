# Lab 3 — Guardrails for Agents That Act · expected output

Labs 1 and 2 built an agent that is right. This lab is about an agent that is
right and *also* cannot quietly take production down while being right.

Four independent layers. Any one of them alone is a single point of failure.

---

## Layer 4 first — scoped credentials

Start here, because it is the only layer that holds when the other three fail.
Layers 1–3 live in our Python process. This one lives in the API server.

```
$ make lab3 ARGS='--rbac-demo'
```

```
Who is the agent?
ATTRIBUTE   VALUE
Username    system:serviceaccount:ml-prod:infra-agent

What is it permitted to do?
  list pods in ml-prod             yes
  list pods in ml-staging          yes
  patch deploy in ml-prod          yes
  patch deploy in ml-staging       no
  read secrets in ml-prod          no
  read pods in kube-system         no
  delete anything in ml-prod       no

And what happens when it tries anyway?
  Error from server (Forbidden): pods is forbidden:
  User "system:serviceaccount:ml-prod:infra-agent" cannot list resource
  "pods" in API group "" in the namespace "kube-system"
```

That refusal came from Kubernetes, not from us. No prompt engineering changes
it, no amount of reasoning gets around it, and it is still true if every other
guardrail in this repo has a bug in it.

Note what is *not* granted: no `delete` anywhere, and no read on Secrets. An
agent that can read pod specs and logs across two namespaces already represents
real trust. One that can read Secrets is a different conversation with your
security team.

---

## Layer 1 — read-only by default

```
$ make break-7
$ make lab3
```

The agent diagnoses the broken rollout, reaches for the rollback tool, and:

```
  -> rollback_deployment(namespace='ml-prod', name='inference-api', dry_run=False)
     REFUSED: rollback_deployment is a write tool and this session is
     read-only. Propose the change and the human will decide whether to
     re-run with --allow-writes. Do not retry.
```

It then completes the investigation and proposes the change in its answer,
citing [RB-012]. Nothing was written. The audit log records the attempt:

```
audit trail — every gated decision
  2026-08-22T19:27:49-0400  rollback_deployment    refused_read_only
```

The refusal is recorded, not just the successes. "What did it try to do" is a
question you will eventually want answered.

---

## Layers 2 and 3 — dry run, then a human

```
$ make lab3 ARGS='--allow-writes'
```

The write tools are now registered. They still cannot apply anything on their
own. The agent dry-runs first, because the tool description tells it to:

```
  -> rollback_deployment(namespace='ml-prod', name='inference-api', dry_run=True)
     DRY RUN — nothing was changed.
     Roll ml-prod/inference-api back one revision.
     - image: inference-stub:v3-broken
     + image: inference-stub:v2
```

Then it asks for the change for real, and the loop stops dead:

```
====================================================================
  APPROVAL REQUIRED
====================================================================

  tool      rollback_deployment
  arguments {'namespace': 'ml-prod', 'name': 'inference-api', 'dry_run': False}

  what this will do
    Roll ml-prod/inference-api back one revision, replacing the current
    image with the previous one. Pods will be recreated.

  change
      deployment ml-prod/inference-api
    - image: inference-stub:v3-broken
    + image: inference-stub:v2

    deployment.apps/inference-api
    REVISION  CHANGE-CAUSE
    17        <none>
    18        <none>

====================================================================
Apply this change to production? Type 'y' to proceed:
```

The prompt shows the resource, the exact change, and the revision history. It
is never "allow this action? y/n" with no object — a human cannot approve what
they cannot see.

Type anything other than a literal `y` and it aborts:

```
DENIED by human operator. The change was not applied.
```

Type `y` and it applies:

```
APPLIED: deployment.apps/inference-api rolled back
```

Confirm for yourself:

```
$ kubectl -n ml-prod get deploy inference-api -o jsonpath='{..image}'
inference-stub:v2
```

---

## The audit log

`audit.jsonl`, one JSON object per line, appended. Tail it in a second pane
while the agent works:

```
$ tail -f audit.jsonl
```

A full scenario-07 run:

```
list_pods              dry_run=False  n/a
get_events             dry_run=False  n/a
get_deployment         dry_run=False  n/a
rollback_deployment    dry_run=True   not_required
rollback_deployment    dry_run=False  granted        APPLIED: deployment rolled back
```

Reads are logged too, not just writes. A log that records only the dangerous
operations cannot answer *what did it look at before it decided that* — which
is the question you actually have at 3am.

---

## There is no bypass flag

No `--yes`. No `--force`. No environment variable. `tests/test_guardrails.py`
walks the AST of every shipped file and fails the build if anyone adds one.

This is deliberate and it is worth arguing about. A gate with a documented
bypass is a gate that gets bypassed in exactly the circumstances it exists for:
a noisy incident, at 3am, by someone who has already approved forty of these
today and has stopped reading them.

The approval check accepts a literal `y` and nothing else — not `yes`, not `Y`,
not an empty line. A closed stdin (a pipe, a CI runner, a detached terminal)
raises EOF and is treated as a refusal. It fails closed.

---

## Try this

- Run `make lab3 ARGS='--allow-writes'` and type `n`. Watch the agent accept
  the refusal and stop rather than looking for another route to the same
  change — the system prompt tells it that being refused is the system working.
- Ask it to do something in `ml-staging` and watch two independent layers
  refuse: our namespace scope, and the RBAC Role.
- Comment out the `allow_writes` check in `agent/guardrails.py` and re-run the
  RBAC demo. The API server still refuses. That is the layer worth having.
