# Troubleshooting

**Start here:**

```bash
make doctor      # is my machine set up correctly?
make verify      # is my cluster healthy?
make reset       # fix almost anything, in ~20 seconds
```

`make reset` is not a last resort. Run it between exercises, run it whenever
something looks odd, and run it if you think you've broken your cluster. **You
cannot break it in a way reset won't fix** — and if you somehow do,
`make clean && make cluster` rebuilds from nothing in under two minutes.

---

## Setup

**`make doctor` says FAIL on Python, and I have 3.14**
Expected. This repo needs 3.11–3.13; the session description saying "3.11+" is
imprecise and that's on us. You don't need to change your system Python —
install one alongside it and `make setup` finds it:
`brew install python@3.12` or `sudo apt install python3.12-venv`.

**`make doctor` says Tier B and I do have Docker**
The daemon isn't reachable, not that Docker isn't installed. Start Docker
Desktop and re-run. On Linux you may need `sudo usermod -aG docker $USER`, then
log out and back in.

**`make setup` fails on `kind`**
On macOS it uses Homebrew. Without it, install kind manually from
<https://kind.sigs.k8s.io/docs/user/quick-start/#installation> and re-run.

**`ModuleNotFoundError` on any lab**
Dependencies aren't installed, or you're not using the venv. Run `make setup`.
Always invoke labs through `make lab1`, not `python labs/...` — the Makefile
uses `.venv/bin/python`.

**`make: *** No rule to make target`**
You're not in the repository root. `cd` to the folder containing `Makefile`.

---

## Cluster

**`make cluster` hangs or times out**
Usually Docker memory. Docker Desktop → Settings → Resources → **8 GB**. Then
`make clean && make cluster`.

**Pods stuck `ImagePullBackOff` on `inference-stub`**
The local image didn't load into the cluster. `make clean && make cluster`
rebuilds and re-loads it. This image is **never** pulled from a registry — it's
built on your machine, which is why the labs work identically on Apple Silicon,
x86 and WSL2.

**`make verify` fails on "Prometheus has stub metrics"**
Prometheus scrapes every 10s and needs a cycle or two. Wait 30 seconds and
re-run. If it persists, `make reset`.

**GPU row fails after my laptop slept**
Extended resources set on a node don't survive a kubelet restart. `verify.sh`
re-applies them automatically — just run `make verify` again.

**Everything is Pending / nothing schedules**
Docker ran out of memory or disk. Check `docker system df`, then
`docker system prune` if you're tight, and rebuild.

---

## The labs

**Lab 1 gives me a ranking but no answer**
That's the no-API-key path, and it's fine — the ranking is what Lab 1 is about.
Add `--retrieval-only` to make it explicit, or put a key in `.env`.

**`NoCredentials`**
`cp .env.example .env` and add `ANTHROPIC_API_KEY=...`. Confirm with
`make doctor`.

**401 / authentication_error**
The key is present but wrong, revoked, or has no credit. Check at
<https://console.anthropic.com/settings/keys>.

**My scores differ from `EXPECTED.md`**
They shouldn't — BM25 over a fixed corpus is deterministic. Check you haven't
edited anything in `runbooks/`. `git status` will tell you.

**My agent's answer differs from `EXPECTED.md`**
**Expected, and not a bug.** The model is non-deterministic. The *tool sequence*
and the *conclusion* should match; the prose won't. Scenario 01 should always
land on `MODEL_CONFIG_PATH` and RB-014, but it may reach that from the pod
logs or from `describe_pod`'s termination reason.

**The agent says nothing is wrong**
The fault didn't land. Every `make break-N` now waits until its own fault is
visible, so this should be rare — but `make reset && make break-N` and try
again.

**The agent stopped after 12 iterations**
It ran out of budget without converging, usually because several faults are
stacked. `make reset`, inject one fault, retry.

**Scenario 04 looks like nothing happened**
That fault takes 25–90 seconds to appear, because it depends on Prometheus'
rate window moving. `make break-4` blocks until it's real — if you injected it
another way, wait a minute.

**Lab 3 never shows me the approval prompt**
The agent only dry-ran. Ask it explicitly to apply the rollback, or re-run.
Dry runs deliberately never reach the gate.

**Lab 4 sweep seems stuck**
A full sweep is ~8 minutes: eight cases, each an agent run plus a settle. Use
`make lab4 ARGS='--replay'` for the instant version.

---

## Cost

Each agent run is roughly **$0.28** on `claude-opus-5` at default effort. A full
pass through all four labs is about **$1.00–1.50**. The only expensive thing is
a live Lab 4 sweep (~$2.25), which is why `--replay` exists.

Set `AGENT_MODEL=claude-sonnet-5` in `.env` for a cheaper run. Note that every
published figure here is measured on Opus 5, so treat Sonnet as untested rather
than characterised.

---

## Still stuck

1. `make reset` — genuinely fixes most things
2. `make clean && make cluster` — under two minutes from nothing
3. `make doctor` and `make verify` — paste both outputs when you ask for help
4. Every lab's `EXPECTED.md` shows what it looks like when it works

Nothing here expires. If today isn't the day, the repository will behave
identically next month.
