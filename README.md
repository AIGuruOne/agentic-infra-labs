# agentic-infra-labs

Lab repository for **Agentic AI for Infrastructure Engineering: From Chatbots to
Operators** — AI Guru® × Packt, 27 August 2026.

An AI agent that investigates a live Kubernetes cluster: reads pod events,
correlates Prometheus metrics, cites runbooks, and proposes remediation behind
an approval gate. Entirely on your laptop. No cloud account, no GPU.

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
make cluster     # ~1m30s from clean on an M-series Mac, under 5 minutes anywhere
```

### Tier B — no Docker on this machine

Locked-down work laptop, no admin rights, corporate policy. **This is fine.**
Follow the session on screen and run the labs later from a machine that allows
Docker. Nothing here expires, nothing is time-limited, and the repository is
yours to keep.

Lab 1 runs with no cluster and no Docker at all — just Python. Start there.

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
```

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
|---|---|
| Docker | ~8 GB allocated. Measured peak is well under that — see [VERSIONS.md](VERSIONS.md) |
| Disk | 10 GB free |
| Python | 3.11–3.13. Not 3.14: the pinned wheels have no 3.14 build |
| LLM key | `ANTHROPIC_API_KEY`. OpenAI works as a documented fallback |
| Kubernetes | pods, deployments, services, namespaces. Nothing exotic |

`kind` and `kubectl` are installed by `make setup` if missing.

---

## The four labs

**Lab 1 — the knowledge layer.** BM25 over 14 runbooks with a hard pre-filter on
frontmatter metadata. Run the same question with and without the filter and get
two different runbooks with two different remediations, one of which causes an
outage. This is the shortest path to understanding why retrieval quality is not
a ranking problem.

**Lab 2 — the agent meets the cluster.** Two MCP servers (Kubernetes and
Prometheus, 13 tools) and a raw agent loop against the Messages API. No
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
|---|---|---|
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
scripts/        doctor, setup, cluster, verify
cluster/        kind config, GPU simulation, scoped agent RBAC
workloads/      inference stub (stdlib only) + manifests
observability/  a single Prometheus Deployment, plus metrics-server
runbooks/       14 markdown runbooks with YAML frontmatter
faults/         break-1..7 and reset
labs/           the four labs, each with an EXPECTED.md
mcp/            k8s and Prometheus MCP servers
agent/          loop, provider seam, guardrails, audit log
tests/          what must not silently break
```

---

## A note on the model

The canonical path is the raw Anthropic Messages API with the MCP Python SDK.
No agent framework anywhere in `/labs` — what you learn here survives the next
framework churn cycle, because there is nothing to churn.

`AGENT_MODEL` and `AGENT_EFFORT` in `.env` control cost and depth. The default
is `claude-opus-5` at `medium` effort, which costs about **$0.30 per scenario**
and roughly **$1.00–1.50 for a full pass through all four labs** — measured, not
estimated, from the committed eval scorecard. `claude-sonnet-5` is materially
cheaper and handles most scenarios. Full breakdown in [VERSIONS.md](VERSIONS.md).

The OpenAI path is a real, tested fallback rather than an aspiration — run any
lab with `--provider openai`. It is not what the session teaches.

---

## Licence and ownership

See [LICENSE.md](LICENSE.md).

---

*AI Guru® · [aiguru.one](https://aiguru.one) · © 2026 Keyom Inc.*
