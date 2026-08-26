# Lab 3 — Guardrails
## What to do · 15 minutes

Demonstrated live in the session; this is how you re-run it yourself.

**You need:** a cluster and an API key. Three agent runs, ~82s and ~$0.30 each.

---

## 1 · Who is the agent?  · 2 min · no API key needed

```bash
make lab3 ARGS='--rbac-demo'
```

**You should see** the agent's identity — `system:serviceaccount:ml-prod:infra-agent`
— then seven permission checks, then a real 403.

**That refusal comes from the Kubernetes API server, not from this repo's code.**
Every other guardrail here is something we wrote and could have got wrong. This
one is enforced somewhere the agent cannot reach.

Look at what it *cannot* do: read Secrets, touch staging, delete anything
anywhere. Then read the Role that produces that:

```bash
less cluster/rbac/agent-sa.yaml
```

The verb list is where the thinking is. `patch` but not `delete` is a
deliberate line you could defend to a security reviewer.

---

## 2 · Read-only refuses  · 4 min

```bash
make reset && make break-7
make lab3
```

**You should see** the agent diagnose the bad image tag, reach for
`rollback_deployment`, get `REFUSED`, and then *propose* the change in its
answer instead of retrying.

```bash
tail -3 audit.jsonl
```

The refusal is logged, not just the approvals. The question you have at 3am is
what it **tried** to do.

---

## 3 · The approval gate  · 6 min

```bash
make lab3 ARGS='--allow-writes'
```

It dry-runs first, then asks for real and **stops**.

**Type `n`.** It aborts, nothing changes.

Run it again and **type `y`**, then check:

```bash
kubectl -n ml-prod get deploy inference-api -o jsonpath='{..image}' ; echo
```

**You should see** `inference-stub:v2` — rolled back from `v3-broken`.

---

## 4 · Try to get around it  · 3 min

Genuinely try. Then read why you can't:

```bash
grep -n "REQUIRED_ARGS\|refused_unsafe\|_approve" agent/guardrails.py | head
.venv/bin/python -m pytest tests/test_guardrails.py -v 2>&1 | head -20
```

Things worth knowing:

- only a literal `y` approves — not `yes`, not `Y`, not an empty line
- closed stdin (a pipe, a cron job) raises EOF and is treated as **refusal**
- scaling to zero is refused *before* a human is ever asked
- there is no bypass flag, and a test walks the AST of every shipped file to
  keep it that way

---

## If something doesn't work

| | |
|---|---|
| No approval prompt appears | The agent only dry-ran. Ask it explicitly to apply the rollback. |
| `REFUSED: ... read-only` | Expected without `--allow-writes`. That's task 2. |
| `ERROR: could not read ... to build a preview` | The deployment isn't there. `make reset`. |
| audit.jsonl missing | It's created on first tool call, at the repo root. |

---

## The honest caveat

These four layers are **illustrative of an approach, not a security product**.
The only one enforced outside the agent's own process is the Kubernetes RBAC.
Review and adapt before carrying any of it into production.
