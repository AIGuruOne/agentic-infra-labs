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
| `make cluster` from clean | **44 s** | under 5 min |
| Peak container RAM under load | **1.46 GiB** | under 6 GB |
| — control-plane | 779 MiB | |
| — worker | 539 MiB | |
| — worker2 (GPU pool) | 196 MiB | |
| p95 inference latency, healthy | **24 ms** | |
| p95 under `break-4` | **488 ms** | visibly different |
| CFS throttling under `break-4` | **0.22 s/s** | non-zero and legible |

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

A single scenario is 3–5 agent iterations. Measured on the OpenAI fallback path
(gpt-4o), a scenario costs roughly 10k–15k input tokens and 200–1,000 output
tokens in total across those iterations, dominated by tool results rather than
by reasoning.

At `claude-opus-5` list pricing ($5/MTok in, $25/MTok out) that is on the order
of **$0.05–0.10 per scenario**, so a full four-lab pass is well under a dollar.
`claude-sonnet-5` is meaningfully cheaper and handles every scenario except
arguably scenario 02, which rewards a stronger model because it requires finding
two causes rather than stopping at the first.

The full eight-case eval sweep is the only expensive operation here, which is
why `make lab4 ARGS='--replay'` exists and why the sweep is never run live.
