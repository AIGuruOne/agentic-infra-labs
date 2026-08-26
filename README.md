# agentic-infra-labs

Lab repository for **Agentic AI for Infrastructure Engineering: From Chatbots to
Operators** — AI Guru® × Packt, 27 August 2026.

An AI agent that investigates a live Kubernetes cluster: reads pod events,
correlates Prometheus metrics, cites runbooks, and proposes remediation behind
an approval gate. Entirely on your laptop. No cloud account, no GPU.

**Lab 1 needs no Docker and no cluster — just Python.** If your machine won't run
Docker, you can still run the lab that carries the session's central lesson.

---

## Before the session

Two of these take minutes. Two can take days, so start them now.

| | |
| --- | --- |
| **Days** | **An LLM API key with credit on it.** Budget **up to $5** for the whole session — most people spend less. Create a *fresh* key with a spend limit rather than reusing a production one. If you're expensing it, that's a purchasing conversation, so start today. |
| **Days** | **Confirm you're allowed to run Docker on the machine you'll actually use.** Not whether it's installed — whether policy permits it. On a managed laptop that's an IT ticket. |
| **Minutes** | Clone this repository and run `make doctor`. It tells you your tier and exactly what, if anything, is missing. |
| **Minutes** | Tier A only: run `make cluster` once, then `make clean`. The first run pulls container images; doing that on Wednesday means Thursday's run comes off a warm cache. |

If `make doctor` says Tier B or C, that is a complete answer, not a problem. Read
on.

> ### ⚠️ Note on the Python version
>
> **The session description says "Python 3.11+". This repository needs Python
> 3.11, 3.12 or 3.13 — not 3.14.**
>
> That imprecision is ours, not a fault on your machine. If `make doctor`
> reports `FAIL` on the Python row and you have 3.14, you have found this
> discrepancy — your setup is fine.
>
> The reason: every dependency here is pinned so that someone running this in
> 2027 reproduces what the recording shows. Two of those pins — `kubernetes` and
> `mcp` — have no prebuilt 3.14 wheel, so installing on 3.14 means compiling
> from source. That is slow and it fails in ways that are miserable to debug on
> the morning of a session.
>
> **Fix — you do not need to change or remove your system Python.** Install one
> of 3.11–3.13 alongside it; `scripts/setup.sh` finds a supported interpreter
> and builds an isolated `.venv` from it:
>
> ```bash
> brew install python@3.12            # macOS
> sudo apt install python3.12-venv    # Debian / Ubuntu
> ```
>
> Then re-run `make doctor` — it reports which interpreter it selected.

---

**Something not working?** [TROUBLESHOOTING.md](TROUBLESHOOTING.md) covers the
failures we actually hit building this. `make reset` fixes most of them in
20 seconds.

---

## Which tier are you?

Not "Installation." This first, because the most common feeling at minute 15 of
a live session is *"I'm falling behind and everyone else is fine."* You are not,
and this section exists to make that feeling impossible before it starts.

```bash
./scripts/doctor.sh      # or: make doctor
```

It prints a PASS/FAIL table and ends with your tier.

### Tier A — Docker is available

You can run everything live. Before the session:

```bash
make setup       # installs kind, kubectl, and a Python venv
make cluster     # ~1m41s from clean on an M-series Mac, under 5 minutes anywhere
```

### Tier B — no Docker on this machine

Locked-down work laptop, no admin rights, corporate policy. **This is fine.**

**Start with Lab 1.** It runs on Python alone — no Docker, no cluster, no
containers — and it is the lab that demonstrates why retrieval quality is not a
ranking problem. You are not watching passively.

```bash
make setup      # notices Docker is absent and sets up Python anyway
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --environment prod --namespace ml-prod'
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --no-metadata-filter'
```

Run those two back to back. The difference between them is the point of the
first hour.

For Labs 2 through 4, follow the session on screen and run them later from a
machine that allows Docker. Nothing here expires, nothing is time-limited, and
the repository is yours to keep.

### Tier C — reading, not running

Every lab has an `EXPECTED.md` containing real captured output with the
reasoning explained. You can follow the entire session, and understand every
result, without running a single command:

- [Lab 1 — the knowledge layer](labs/lab1-knowledge-layer/EXPECTED.md)
- [Lab 2 — the agent meets the cluster](labs/lab2-live-state-agent/EXPECTED.md)
- [Lab 3 — guardrails](labs/lab3-guardrails/EXPECTED.md)
- [Lab 4 — evaluating the agent](labs/lab4-evals/EXPECTED.md)

**Following along live is optional.** It always was.

---

## Quickstart

```bash
git clone https://github.com/AIGuruOne/agentic-infra-labs
cd agentic-infra-labs

make doctor                       # what tier am I?
make setup                        # tooling + venv
cp .env.example .env              # add your ANTHROPIC_API_KEY
make cluster                      # 3-node kind cluster, workloads, Prometheus
make verify                       # health table, should be all-PASS
make tour                         # what IS all this? start here
```

**Run `make tour` before your first lab.** Every lab from there asks you to
reason about `ml-prod`, `inference-api` and a GPU node; the tour shows you what
those actually are, on your own cluster. It works without a cluster too — the
runbook half is all Lab 1 needs.

Then work through the labs in order:

```bash
make lab1 ARGS='"why are prod inference pods restarting?" --environment prod --namespace ml-prod'
make break-1 && make lab2 ARGS='--scenario 1'
make break-7 && make lab3 ARGS='--allow-writes'
make lab4 ARGS='--replay'
```

`make reset` returns to a healthy baseline from any combination of faults,
without rebuilding. `make clean` deletes the cluster.

---

## What you need

| | |
| ---------- | ---------------------------------------------------------------------------------- |
| Docker | ~8 GB allocated. Measured peak is **1.29 GiB** — well under — see [VERSIONS.md](VERSIONS.md) |
| Disk | 10 GB free |
| Python | **3.11–3.13. Not 3.14** — see [the note above](#-note-on-the-python-version). You do not need to change your system Python |
| LLM key | `ANTHROPIC_API_KEY`. OpenAI works as a documented, tested fallback |
| Network | Outbound HTTPS to `api.anthropic.com`. Corporate proxies and TLS inspection can block this, and the failure looks like a hang rather than an error — `make doctor` checks it explicitly |
| Kubernetes | pods, deployments, services, namespaces. Nothing exotic |

`kind` and `kubectl` are installed by `make setup` if missing.

**Not required:** a cloud account, a GPU, an existing Kubernetes cluster,
cluster-admin rights anywhere, or any prior AI or ML experience.

---

## The four labs

Each lab folder has two files:

| | |
|---|---|
| **`LAB.md`** | **what to do** — numbered tasks, the commands, and what you should see |
| `EXPECTED.md` | what it looks like when it works, with the reasoning explained |

Open `LAB.md` and work down it. `make lab1` and friends print the paths too.


**Lab 1 — the knowledge layer.** BM25 over 14 runbooks with a hard pre-filter on
frontmatter metadata — environment, cluster, namespace, service, model, GPU
type, provider and region, each its own CLI flag. Run the same question with and
without the filter and get two different runbooks with two different
remediations, one of which causes an outage. This is the shortest path to
understanding why retrieval quality is not a ranking problem. Runs without
Docker.

**Lab 2 — the agent meets the cluster.** Two MCP servers (Kubernetes and
Prometheus, 12 tools) and a raw agent loop against the Messages API. No
framework. The loop is about forty lines and prints every step as it happens,
because on a screen share the loop being visible is the lesson.

**Lab 3 — guardrails.** Read-only by default, dry-run-first, human approval on a
literal `y`, and a scoped ServiceAccount. Four layers, because any one alone is
a single point of failure. There is no bypass flag and a test enforces that.

**Lab 4 — evaluating the agent.** Eight incident cases scored against
assertions. Case 8 is designed to fail: it asks the same question as case 1 with
metadata filtering off, and the agent answers fluently, cites correctly, and
recommends deleting a production ConfigMap.

---

## The seven faults

Every fault is injected by a script. Nothing is done by hand, so a buyer running
this in March 2027 reproduces exactly what the recording shows.

| | scenario | what breaks |
| -------------- | ------------------- | ------------------------------------------------------ |
| `make break-1` | pods restarting | `MODEL_CONFIG_PATH` points at a file not in the image |
| `make break-2` | GPU scheduling | 4 GPUs requested, 2 available, and no toleration |
| `make break-3` | namespace discovery | a decoy Service in `ml-staging` annotated "production" |
| `make break-4` | latency spike | 250ms CPU burn per request, CPU limit cut to 50m |
| `make break-5` | autoscaling | HPA targets 95% CPU with min == max |
| `make break-6` | cross-env drift | staging diverges in tag, revision, and error rate |
| `make break-7` | rollback | rolled onto an image tag that does not exist |

`make reset` undoes any combination of them in one command.

---

## Repository layout

```
scripts/        doctor, setup, tour, cluster, verify
cluster/        kind config, GPU simulation, scoped agent RBAC
workloads/      inference stub (stdlib only) + manifests
observability/  a single Prometheus Deployment, plus metrics-server
runbooks/       14 markdown runbooks with YAML frontmatter
faults/         break-1..7 and reset
labs/           the four labs · LAB.md (what to do) + EXPECTED.md (what you'll see)
mcp/            k8s and Prometheus MCP servers
agent/          loop, provider seam, guardrails, audit log
alt/langgraph/  frozen LangGraph reference port — not maintained
tests/          what must not silently break
TROUBLESHOOTING.md  when something does not work
GLOSSARY.md     every term the session uses, defined
```

---

## A note on the model

The canonical path is the raw Anthropic Messages API with the MCP Python SDK.
No agent framework anywhere in `/labs` — what you learn here survives the next
framework churn cycle, because there is nothing to churn.

`AGENT_MODEL` and `AGENT_EFFORT` in `.env` control cost and depth. The default
is `claude-opus-5` at `medium` effort. **Budget up to $5 for the full session**;
most people spend well under that, and the per-scenario and per-lab breakdown is
in [VERSIONS.md](VERSIONS.md), measured rather than estimated.

`claude-sonnet-5` is materially cheaper. Every published figure here is measured
on `claude-opus-5` only, so treat Sonnet as untested rather than characterised:
expect a shallower investigation and output that will not match the recording
step for step.

The OpenAI path is a real, tested fallback rather than an aspiration — run any
lab with `--provider openai`. It is not what the session teaches.

---

## Glossary

[GLOSSARY.md](GLOSSARY.md) defines every term the session uses without stopping
to explain it — context window, grounding, BM25, MCP, tool calling, xfail. The
Kubernetes and observability terms are assumed; the AI terms are not. Written so
that someone arriving from the recording with a different background can follow
the whole session.

---

## Licence

**MIT** — see [LICENSE](LICENSE), with third-party and trademark notes in
[LICENSE.md](LICENSE.md). Use it, change it, ship it inside your own systems,
teach from it.

One carve-out: `observability/metrics-server.yaml` is vendored from
kubernetes-sigs/metrics-server and stays under Apache 2.0.

---

*AI Guru® · [aiguru.one](https://aiguru.one) · © 2026 Keyom Inc.*
