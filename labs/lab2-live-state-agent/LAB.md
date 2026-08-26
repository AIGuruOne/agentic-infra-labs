# Lab 2 — The Agent Meets the Cluster
## What to do · 25 minutes

**You need:** a running cluster (`make verify` → ALL PASS) and an API key in
`.env`. Each agent run costs roughly **$0.30** and takes **40–90 seconds**.

**No cluster or no key?** Skip to the bottom — `EXPECTED.md` has every run
captured, and task 4 is readable without either.

---

## 1 · Scenario 01 — pods restarting  · 5 min

```bash
make reset
make break-1
make lab2 ARGS='--scenario 1'
```

**You should see** the agent make 4–7 tool calls and conclude that
`MODEL_CONFIG_PATH` points at a file that isn't in the image, citing `RB-014`
and proposing `rollout undo`.

### Watch the tool calls, not the answer

This is the whole point of the task. Three things to notice:

1. It called `list_pods` **first** — to find which single pod was worth
   investigating, before spending tokens on anything expensive.
2. It called `describe_pod` on **one** pod, not four.
3. It called `get_pod_logs` with **`previous=True`**.

Nothing in the prompt mentions crashloops. Find out why it knew:

```bash
grep -B2 -A4 "previous=True" mcp/k8s_mcp.py
```

**One sentence in a docstring bought a correct diagnosis.**

---

## 2 · Scenario 02 — the two-cause one  · 5 min

```bash
make reset
make break-2
make lab2 ARGS='--scenario 2'
```

**You should see** the agent find **both** causes:

- the pod requests 4 GPUs and the only GPU node advertises 2
- the pod has no toleration for that node's taint

**Does yours find both?** If it stops at one, that's the failure mode this whole
session is about — an answer that's correct as far as it goes, and incomplete in
a way nothing flags.

Now read what the scheduler actually said:

```bash
kubectl -n ml-prod get events --field-selector reason=FailedScheduling \
  -o jsonpath='{.items[-1].message}' ; echo
```

Both reasons, in one message. The agent had to read past the first clause.

---

## 3 · Extend the MCP server — part one  · 5 min

Open `mcp/k8s_mcp.py` and find the commented `get_resource_quota` block.

**Read the docstring before you uncomment it.** Notice it doesn't describe the
code — it says what comes back, when to use this *rather than* `get_nodes`, and
what it costs.

Then uncomment the whole block — decorator, def, and body — and re-run:

```bash
make lab2 ARGS='--scenario 2'
```

**You should see** 13 tools instead of 12 in the header line.

> This is deliberately not a writing exercise. The eight lines of implementation
> are the easy half; the docstring is the half that changes behaviour.

---

## 4 · Extend the MCP server — part two · write one  · 10 min

**This one is yours. There's no code to reveal.**

Nothing in the server exposes a Deployment's **rollout history**. The agent can
see what's running now, but not *which revision introduced a change* — the most
useful missing fact in scenarios 01 and 07.

Write `get_rollout_history(namespace, name)`:

- ReplicaSets carry the revision in the annotation
  `deployment.kubernetes.io/revision`
- `apps.list_namespaced_replica_set(namespace, label_selector=f"app={name}")`
- The agent's Role already permits reading them — no RBAC change needed

**Write the docstring first.** Make it answer the same three questions every
other tool answers: what it returns, when to use it rather than
`get_deployment`, what it costs.

Then:

```bash
make reset && make break-1
make lab2 ARGS='--scenario 1'
```

**Does the model call your tool without being told to?**

If it doesn't — change the docstring, not the code. That's the lesson of this
whole segment, and here you get to test it on something you wrote.

> **Stuck, or out of time?** A worked solution is at the bottom of
> `EXPECTED.md`. Try it first — the interesting variation is in the docstring,
> and there's more than one good answer.

---

## If something doesn't work

| | |
|---|---|
| `NoCredentials` | Your key isn't in `.env`. `make doctor` will confirm. |
| 401 / authentication error | Key is set but wrong, or has no credit. |
| `ERROR: no usable Kubernetes credentials` | `make cluster` first. |
| Agent gives up after 12 iterations | Usually several faults stacked. `make reset`, inject one, retry. |
| Pods aren't crashlooping after `break-1` | Give it ~10 seconds. `kubectl -n ml-prod get pods -w` |
| Answer differs from `EXPECTED.md` | Expected. The **tool sequence** and the **conclusion** should match; the prose won't. |
| Everything is weird | `make reset`. It fixes almost everything, in 20 seconds. |

---

## Done early?

Delete the `previous=True` sentence from `get_pod_logs`'s docstring in
`mcp/k8s_mcp.py`, then re-run scenario 01.

**Watch what breaks.** The code is untouched — you changed only a comment — and
the diagnosis gets worse. That's the most direct demonstration in this repo that
tool descriptions *are* the prompt.

(Put the sentence back afterwards.)

---

## Not running anything?

`EXPECTED.md` in this folder has both scenarios captured with the reasoning
explained, plus the full worked solution for task 4.
