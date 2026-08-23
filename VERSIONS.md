# Versions, pins, and measured numbers

Everything here is pinned so a buyer running this in March 2027 reproduces what
the August 2026 recording shows. Where a pin is a judgement call rather than
"the current release", the reason is written down.

Measured on the reference machine: **Apple Silicon Mac, Docker Desktop with 7.8
GiB allocated.**

---

## Measured

| | measured | budget |
|---|---|---|
| `make cluster` from clean (no cached kind image) | **1 m 41 s** | under 5 min |
| `make cluster` reusing an existing cluster | **44 s** | |
| Peak container RAM under load | **1.29 GiB** | under 6 GB |
| p95 inference latency, healthy | **24 ms** | |
| p95 under `break-4` | **488 ms** | visibly different |
| CFS throttling under `break-4` | **0.20 s/s** | non-zero and legible |

**These figures were re-measured after a bug that invalidated the originals.**
`make reset` could not remove environment variables that a break script added
with `kubectl set env`, because `set env` does not update
last-applied-configuration and a three-way merge emits no delete directive for
an entry present only in the live object. `break-4`'s `CPU_BURN_MS=250`
therefore persisted through every reset, so the cluster's "baseline" p95 was
488 ms rather than 24 ms — meaning scenario 04's latency *step change*, the
whole point of the scenario, could never actually be observed. The manifests
now declare every variable the faults touch, and a test enforces it.

**On the RAM figure.** 1.46 GiB is what `docker stats` reports for the three
kind containers, which is the number the 6 GB budget is about. On macOS this is
measured inside the Docker VM and excludes the VM's own overhead — the honest
whole-machine figure is that Docker Desktop is configured with 7.8 GiB and the
labs use a fraction of it. On Linux, where containers run on the host kernel,
`docker stats` is the whole story.

The budget is not tight. That is deliberate: it is what was bought by running a
single plain Prometheus Deployment instead of kube-prometheus, and by an
inference stub that imports nothing outside the standard library.

---

## Tooling

| | pin | why |
|---|---|---|
| kind | v0.32.0 | installed by `setup.sh`; v0.30.0 is the floor for the node-status patch path |
| Kubernetes (kind node) | v1.35.0 | whatever kind v0.32.0 ships |
| Docker | 28.1.1 | tested; anything 24+ should work |
| Python | 3.11–3.13 | **not 3.14** — see below |

**Why not Python 3.14.** The pinned `kubernetes` and `mcp` wheels have no 3.14
build. Installing on 3.14 means a source compile, which is a slow and
failure-prone thing to discover on the morning of a session.
`scripts/lib/pick-python.sh` is the single place that selects the interpreter,
sourced by both `doctor.sh` and `setup.sh` so they can never disagree. It
prefers 3.12, which has a prebuilt wheel for every pin here.

---

## Python dependencies

Pinned in `requirements.txt`.

| package | pin | note |
|---|---|---|
| `anthropic` | 1.0.0 | SDK 1.x. Adaptive thinking, `output_config.effort` |
| `mcp` | 2.0.0 | **`MCPServer`, not `FastMCP`** — see below |
| `kubernetes` | 36.0.3 | official client |
| `rank-bm25` | 0.2.2 | pure Python, no compiled extension, no model download |
| `PyYAML` | 6.0.3 | runbook frontmatter and eval cases |
| `requests` | 2.34.2 | |
| `rich` | 15.0.0 | |
| `pytest` | 9.1.1 | dev/CI only |

**MCP SDK 2.0 is not the API most tutorials show.** `FastMCP` is gone, replaced
by `mcp.server.MCPServer` — same decorator ergonomics, different import. And
`Tool.inputSchema` is now `Tool.input_schema`. If you have MCP code from 2025,
those two renames are most of the migration.

---

## Container images

| image | pin | note |
|---|---|---|
| `prom/prometheus` | v3.6.0 | single Deployment, no Helm, 2h retention |
| `registry.k8s.io/metrics-server` | v0.8.0 | vendored into `observability/metrics-server.yaml` and patched with `--kubelet-insecure-tls` for kind |
| `python` | 3.12-slim | base for the inference stub |
| `inference-stub` | v1 / v2 | **built locally, never pulled** |

The stub is built with `docker build` and side-loaded via `kind load
docker-image`. That single decision is why this repo works identically on Apple
Silicon, x86 Linux, and WSL2 without an attendee ever thinking about CPU
architecture. `v1` and `v2` are the same image under two tags; the tag drift
between prod and staging is scenario 06.

metrics-server is vendored rather than fetched at cluster-creation time so the
bytes are the ones we tested against, not whatever the release URL serves later.

---

## Design decisions worth recording

**Single Prometheus, not kube-prometheus.** Grafana plus Alertmanager on a
3-node kind cluster is what pushes an 8 GB laptop into swap, and nothing from
either appears in the session. The agent queries Prometheus over HTTP through an
MCP tool; it has no use for a dashboard.

**BM25 + metadata pre-filter, no vector database.** No embedding model, no
download, no ONNX runtime, and a demo that is legible on a screen share: a
lexical retriever misled by two near-identical runbooks is *visible*, where an
embedding score changing by 0.03 is not. Swapping in dense retrieval would
change which near-identical document wins by a few points of similarity and
would not change the fact that the wrong environment's runbook is still in the
candidate set. See `labs/lab1-knowledge-layer/EXPECTED.md`.

**GPU simulation by node-status patch.** No device plugin, no NVIDIA runtime.
`cluster/gpu-sim/patch-node.sh` PATCHes `nvidia.com/gpu: "2"` onto the node
status through `kubectl proxy`. These patches do not survive a kubelet restart,
so `verify.sh` re-applies rather than failing — a laptop that slept overnight
would otherwise wake up broken.

**CPU-bound latency injection.** `break-4` uses `CPU_BURN_MS`, not a sleep. A
sleeping process is never throttled by a CPU limit, so a sleep-based "latency
spike" would have the agent hunting for throttling evidence that does not exist.
The demo has to be true about its own mechanism.

---

## Model and cost

Default `claude-opus-5` at `effort: medium`, both settable in `.env`.

**Measured**, from the committed eval scorecard — a real eight-case sweep on
`claude-opus-5`, not an estimate:

| | per scenario (mean) | full 8-case sweep |
|---|---|---|
| input tokens | 40,671 | 325,369 |
| output tokens | 3,117 | 24,942 |
| cost at list price | **$0.28** | **$2.25** |
| agent wall-clock | 58 s | 461 s |

Range across the eight cases: $0.17 (scenario 05, three iterations) to $0.45
(scenario 04, seven iterations and eight distinct tools). Cost is dominated by
input tokens — tool results resent on every iteration — not by reasoning.

A full four-lab pass is roughly **$1.00–1.50**: Lab 1 is a few cents, Lab 2 is
two scenarios, Lab 3 is one, and Lab 4 replays a committed scorecard for free.
Attendees who then explore on their own should budget a few dollars, not a few
cents.

**On model choice.** These numbers are the reason `AGENT_MODEL` is in `.env`.
`claude-sonnet-5` is materially cheaper and handles most scenarios. Scenario 02
is the one that rewards the stronger model: it requires finding *two*
independent causes, and stopping at the first is precisely the confidently-
incomplete failure the session is about.

**On effort.** `medium` is the lab default. Raising it increases both depth and
cost; the measured figures above are all at `medium`.

**A note on the earlier estimate.** An earlier draft of this file estimated
$0.05–0.10 per scenario by extrapolating from a gpt-4o run. That was wrong by
3–6x, because the stronger model investigates far more thoroughly — 5 to 9
distinct tools per case against gpt-4o's 1 to 3. Thoroughness is what you are
paying for and it is worth having; the estimate was simply measuring a
different behaviour. Cost figures here now come from an actual sweep.

The full sweep is the only expensive operation in the repo, which is why
`make lab4 ARGS='--replay'` exists and why the sweep is never run live.
