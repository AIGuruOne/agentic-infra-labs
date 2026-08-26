# Glossary

Every term the session uses without stopping to define it, and a few it defines
in passing. Written for infrastructure engineers: the Kubernetes and
observability terms are assumed, the AI terms are not.

References point to the session segment each term is introduced in.

---

## The model

**Large language model (LLM)**
A program that takes text and produces text. That is the whole interface. It
cannot run a command, open a socket, or reach your cluster. Everything the agent
in this repo does to a cluster is done by Python code in `agent/`, on your
credentials. *(Segment 1)*

**Token**
Roughly three-quarters of a word — the unit a model reads and writes in, and the
unit you are billed in. `CrashLoopBackOff` is several tokens; `the` is one.
*(Segment 8)*

**Context window**
The maximum amount of text a model can read in a single call. It is finite, and
it is the reason retrieval exists: you cannot send the whole runbook corpus, so
something has to choose what goes in. *(Segment 2)*

**Stateless**
The model remembers nothing between calls. The agent loop re-sends the entire
conversation on every iteration — which is why a nine-call investigation costs
much more than nine times a one-call one. *(Segments 1, 8)*

**System prompt**
Standing instructions sent at the top of every call: who the model is, what it
is for, what it must not do. Distinct from the conversation, which is the
back-and-forth of questions and tool results.

**Temperature / nondeterminism**
The same question can produce a different sequence of tool calls on a second
run. This is expected behaviour, not a bug, and it is the reason `make lab4`
exists — "I ran it once and it looked right" is not evidence. *(Segment 7)*

---

## Retrieval

**Retrieval-augmented generation (RAG)**
Four steps: chunk the documents, rank them against the question, select the top
few, and send only those to the model with an instruction to answer from them.
Step 3 discards information, and that is where this session's central failure
lives. Pronounced as a word, and used interchangeably with "retrieval" — if you
have only ever heard it as an acronym, this is all it means. *(Segment 2)*

**Chunk**
A unit of document sent to the model. In this repo a chunk is a whole runbook,
which is the right call for a corpus of short, self-contained documents. Larger
corpora usually split documents into sections.

**BM25**
A lexical ranker — arithmetic over word counts, no model and no vector database.
Rare words count for more, repeated matches have diminishing returns, and
shorter documents score higher for the same match. Decades old, transparent, and
fast enough to run on a laptop in milliseconds. *(Segment 2)*

**Embedding / dense retrieval**
Representing text as a list of numbers so that similar meanings sit close
together, allowing a match on "pods keep dying" against a runbook that says
"CrashLoopBackOff."

**This repo does not use dense retrieval, and that is a deliberate design
decision rather than a gap.** Swapping the ranker changes which of two
near-identical documents wins by a few points of similarity, and does nothing
about the wrong environment's runbook being in the candidate set at all. The
filter is what makes retrieval correct; the ranker only decides the order. It
also costs an embedding model download, which is a poor trade for a lab that
must run on a locked-down laptop. See `labs/lab1-knowledge-layer/EXPECTED.md`
for the long version. *(Segment 2)*

**Metadata filter**
A hard pre-filter on document frontmatter — `environment`, `namespace`,
`cluster` — applied before ranking. It decides which documents are *eligible*.
The ranker only decides their order. *(Segment 2)*

**Frontmatter**
The YAML block at the top of a markdown file. In this corpus it carries the only
signal that distinguishes a production runbook from its near-identical staging
twin, because neither body text mentions its own environment. *(Segments 2, 3)*

**Hybrid retrieval**
Composing retrievers with different blind spots. Here it is lexical plus
structured: BM25 knows what a document is *about* and nothing about where it
applies; the metadata filter knows where it applies and nothing about what it
means. Neither is sufficient alone. *(Segment 2)*

**Grounding**
Requiring the model to answer from documents supplied in this call rather than
from what it absorbed during training. A grounded answer can be checked, because
you can go and read the document it cites. *(Segment 3)*

**Hallucination**
An answer not supported by anything you supplied. Worth distinguishing carefully
from **grounded and wrong**, where the answer faithfully reflects the document
it was given and the pipeline handed it the wrong document. Case 8 in the eval
harness is the second kind, and it is the more dangerous one — every quality
signal you would normally check comes back clean. *(Segments 3, 7)*

---

## Agents and tools

**Agentic**
Describes a system with three things at once: tools it can call, a loop so that
what it sees decides what it looks at next, and a stopping condition so it knows
when it is done. Remove any one and it is something else — tools without a loop
is a plugin, and a loop without a stopping condition is a `while true` you will
regret. *(Segment 1)*

**Agent**
A loop, not a pipeline: observe, plan, act, verify, repeat until the model stops
asking for things. A pipeline runs a fixed set of steps whether or not they
help. A loop has a stopping condition the model controls, which is why scenario
01 finishes in five iterations and scenario 04 takes seven. *(Segments 1, 4)*

**Tool / function calling**
The model emits a structured request naming a function and its arguments. Your
code decides whether to run it, runs it on your credentials, and hands the
output back as text. There is no step at which the model holds a credential.
*(Segment 2)*

**Tool description / docstring**
The only thing the model knows about a tool at the moment it decides whether to
call it. Every tool in this repo answers three questions in its description:
what it returns, when to use it rather than a similar tool, and what it costs.
This is prompt engineering that looks like documentation. *(Segment 2)*

**Model Context Protocol (MCP)**
A standard interface between a model and a system, so an integration is written
once and any host can use it. The two servers in `mcp/` are ordinary stdio MCP
servers with nothing repo-specific about their interface. *(Segment 2)*

**Iteration**
One pass through the agent loop: one model call, plus any tools it requested.
Reported per scenario in the eval scorecard.

**Agent framework**
A library that wraps the loop, tool registration, and state management —
LangGraph, CrewAI and others. This session teaches the raw path because the loop
underneath is about forty lines and does not churn. *(Segment 8)*

---

## Guardrails and evaluation

**Read-only by default**
Write-capable tools are registered but refuse to execute unless the session was
started with `--allow-writes`. *(Segment 6)*

**Dry run**
Executing a change in simulation to produce the diff without applying it. The
agent is instructed to dry-run before proposing anything. *(Segment 6)*

**Approval gate**
A blocking prompt that shows the exact resource and the exact diff and waits for
a literal `y`. Fails closed: `yes`, `Y`, an empty line, and closed stdin are all
refusals. There is no bypass flag, and a test walks the AST of every shipped
file to keep it that way. *(Segment 6)*

**Blast radius**
How much damage a change could do if it were wrong. Every guardrail in Segment 6
is an argument about shrinking it before you need it. *(Segment 6)*

**Scoped credentials**
A dedicated Kubernetes ServiceAccount with a Role limited to two namespaces and
a verb list that excludes `delete` everywhere. The only guardrail enforced
outside the agent's own process — which is why it is the one that still protects
you when the others have bugs. *(Segment 6)*

**Audit log**
`audit.jsonl` — every tool call, its arguments, its result, and any approval
decision. Reads are logged too, because the question you have at 3am is what it
looked at *before* it decided that. *(Segment 6)*

**Eval / eval harness**
A repeatable scored test suite: inject a known fault, ask a known question,
assert on the answer, reset, repeat. Assertions cover the runbook cited, the
root-cause keywords, the remediation type, and what the answer must *not* say.
*(Segment 7)*

**xfail (expected failure)**
A test case designed to fail, which passes the suite by failing in the way it
was designed to. Case 8 is the metadata-blind trap: identical to case 1 except
the retrieval pipeline is stripped of its metadata filter. If case 8 ever
*passes*, the suite reports that as a failure — the trap has stopped working.
*(Segment 7)*

---

## Infrastructure

Assumed knowledge for the live audience, included for anyone arriving from the
recording with a different background.

| Term | In one line |
|---|---|
| **kind** | Kubernetes running inside Docker containers — a disposable cluster on your laptop |
| **Namespace** | A logical partition of a cluster. This repo uses `ml-prod` and `ml-staging` |
| **Pod** | The smallest deployable unit: one or more containers scheduled together |
| **Deployment** | A controller that keeps a specified number of pod replicas running |
| **ReplicaSet** | The object a Deployment creates per revision. A stalled rollout leaves the old one serving, which is why a bad deploy is usually a degradation rather than an outage |
| **CrashLoopBackOff** | A pod that keeps starting, failing, and being restarted with growing delay |
| **Taint / toleration** | A node marker that repels pods, and the pod-side permission to ignore it |
| **HPA** | Horizontal Pod Autoscaler — adds or removes replicas against a metric target |
| **RBAC** | Kubernetes' permission system: who may perform which verb on which resource |
| **ServiceAccount** | The identity a workload authenticates as to the API server |
| **Inference** | Running an already-trained model to get predictions. The lab's `inference-api` is a stub that behaves like any other HTTP workload |
| **Prometheus** | A metrics database that scrapes endpoints and answers range queries |
| **PromQL** | Prometheus' query language. `histogram_quantile(0.95, ...)` is the p95 expression used throughout |
| **p95 latency** | The response time 95% of requests come in under |
| **CPU throttling** | The kernel capping a container at its CPU limit — raises latency without raising load, which is how you tell it apart from a traffic spike |
