# LangGraph reference port

**This is a reference implementation, frozen as of August 2026. It is not
maintained, it is not covered by CI, and it is not the path this session
teaches.**

`/labs` is the supported path. If this directory and `/labs` ever disagree,
`/labs` is right.

---

## Why it exists

To make one teaching point available after the session: *this is what a
framework abstracts.*

Same agent. Same MCP servers. Same runbook retrieval. Same system prompt,
imported verbatim from `agent/loop.py`. The **only** variable is the loop.

```bash
cd alt/langgraph
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python investigate.py --scenario 1     # run `make break-1` first
```

## What the framework removes

| in `agent/loop.py` | here |
|---|---|
| `while` loop over `stop_reason == "tool_use"` | gone |
| appending the assistant turn verbatim | gone |
| batching all tool results into one user message | gone |
| `for step in range(max_iterations)` | `recursion_limit` |
| a normalised `Reply` dataclass per provider | one class swap |

About forty lines, and every one is a line you could get wrong. **We got two of
them wrong while building this repo** — replaying the assistant turn from text
instead of verbatim, and splitting tool results across messages. Both are
silent: the first fails on the next request, the second quietly teaches the
model to stop making parallel calls. A framework would have prevented both.

That is a real argument and it deserves to be made honestly.

## What it costs

**You cannot see the loop.** Segment 4's lesson is that the loop is small and
knowable. Once it is `create_react_agent(...)`, it is neither. Learn it first,
then decide.

**You inherit its dependency graph.** This directory resolves
`anthropic==0.125.0` — the 0.x line — because `langchain-anthropic` pins it,
while `/labs` runs `anthropic==1.0.0`. It also pulls a different `mcp` version.
**That is why this port has its own venv:** installing it alongside `/labs`
silently downgrades the canonical path.

**You inherit its release cadence.** On the day this was written, `langgraph`
1.2.11 already deprecated `create_react_agent` in favour of
`langchain.agents.create_agent`, which lives in a package this port does not
depend on. The file imports the deprecated name deliberately and silences the
warning: chasing the rename would mean adding a dependency to a directory whose
whole point is that it is unmaintained.

**A four-month-old reference port already carries a deprecation.** That is not a
criticism of LangGraph — it is a healthy, fast-moving project. It is the
observation the session is making about where to put your learning.

## When it breaks

**If this stops working against a newer LangGraph, that is expected, not a
defect.** It is pinned in `requirements.txt` to what it was verified against:

```
langgraph==1.2.11
langchain-anthropic==1.6.1
langchain-core==1.6.0
anthropic==0.125.0
```

Install those exact versions and it will behave as it did on the day. Install
newer ones and you are on your own — which is precisely the point being
illustrated.

Nothing in `/labs` depends on this directory. It can rot without affecting
anything you were taught.

## Verified

Scenario 01, end to end, on `claude-opus-5`, 27 August 2026: reads pods, events,
logs with `previous=True`, both deployments, and Prometheus; identifies
`MODEL_CONFIG_PATH` as the sole delta against a healthy pod on an identical
image; cites RB-014; proposes `rollout undo`; and explicitly rules out RB-009's
ConfigMap deletion as harmful in production.

Scenario 02 is also wired up (`--scenario 2`) and was not part of the freeze
gate.

## If your team already uses LangGraph

Use it. You now know what it is doing, which is the only thing this directory
was built to give you.
