# Set up before the session
### 15 minutes, and best done the day before

If you only read one file, read this one. The [README](README.md) is reference;
this is a checklist.

---

## What you're building

Three Docker containers on your laptop, running a real Kubernetes cluster with
two namespaces and a model-serving workload. It deletes with one command and
takes about 1.5 GB of RAM while it runs.

Nothing goes to a cloud. No GPU. No account anywhere except your LLM provider.

---

## Start these now — they can take days

- [ ] **An LLM API key with credit on it.** Budget **up to $5** for the whole
      session; most people spend well under that. Create a *fresh* key with a
      spend limit rather than reusing a production one. If you're expensing it,
      that's a purchasing conversation — start today.
      Anthropic: <https://console.anthropic.com/settings/keys>

- [ ] **Confirm you're *allowed* to run Docker on the machine you'll use.** Not
      whether it's installed — whether policy permits it. On a managed laptop
      that's an IT ticket, and tickets take days.

Everything below takes minutes.

---

## 1 · Clone and check your machine

```bash
git clone https://github.com/AIGuruOne/agentic-infra-labs
cd agentic-infra-labs
make doctor
```

`make doctor` prints a PASS/FAIL table and ends by telling you your **tier**.

| tier | means | what to do |
|---|---|---|
| **A** | Docker works | Everything below. You'll run it all live. |
| **B** | no Docker here | Stop after step 3. Lab 1 needs only Python — and it's the lab carrying the session's main lesson. |
| **C** | not running anything | Nothing to install. Every lab has an `EXPECTED.md` with real captured output. |

**Tier B and C are complete answers, not problems.** Following along live is
optional and always was.

### If doctor says FAIL on Python

You probably have 3.14. This repo needs **3.11–3.13** — the session description
saying "3.11+" is imprecise, and that's on us, not your machine.

You do **not** need to change your system Python. Install one alongside it:

```bash
brew install python@3.12            # macOS
sudo apt install python3.12-venv    # Debian / Ubuntu
```

Then re-run `make doctor`. It reports which interpreter it picked.

---

## 2 · Install the tooling

```bash
make setup
```

Installs `kind` and `kubectl` if missing, builds an isolated Python venv, and
creates a `.env` for you. It's safe to re-run.

**It will not overwrite a `.env` you've already filled in** — and don't run
`cp .env.example .env` yourself, because that would.

---

## 3 · Add your API key

Open `.env` and set:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Confirm it took:

```bash
make doctor      # the LLM API key row should say PASS
```

> Lab 1 works without a key — you'll see the ranking, which is what Lab 1 is
> about. Labs 2–4 need one.

**Tier B stops here.** Skip to *"If you have no cluster"* at the bottom.

---

## 4 · Build the cluster

```bash
make cluster
```

**About 1m40s from cold.** It creates the kind cluster, simulates a GPU node,
builds the inference stub locally, loads it, and deploys everything.

```bash
make verify
```

**Every row should say PASS.** If one doesn't, run `make reset` and re-run.

---

## 5 · See what you've got

```bash
make tour
```

Prints your cluster: the three nodes, the two environments, what
`inference-api` actually is, and the runbook corpus. Every lab from here asks
you to reason about `ml-prod` and a GPU node — this is where you meet them.

---

## 6 · Prove it works, then tear it down

```bash
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --environment prod --namespace ml-prod'
```

You should see `RB-014` as the top hit. If you added a key, you also get a
grounded answer.

Then:

```bash
make clean
```

**Do build it once before the session even though you'll delete it.** The first
run pulls container images; doing that tonight means the morning's run comes off
a warm cache and takes seconds.

---

## On the day

```bash
make cluster && make verify
```

That's it. Come back to `make tour` if you want a refresher.

---

## If you have no cluster (Tier B)

Lab 1 needs nothing but Python:

```bash
make setup
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --environment prod --namespace ml-prod'
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --no-metadata-filter'
```

Run those two back to back. The difference between them is the point of the
first hour, and you don't need a cluster to see it.

`make setup` notices Docker is absent and sets up Python anyway.

---

## When something doesn't work

[TROUBLESHOOTING.md](TROUBLESHOOTING.md) covers the failures we actually hit
building this.

The short version:

```bash
make reset                        # fixes almost anything, ~20 seconds
make clean && make cluster        # from nothing, under two minutes
```

**You cannot break your cluster in a way `make reset` won't fix.** Use it
freely — between exercises, and any time something looks odd.

---

## Checklist

- [ ] `make doctor` → Tier A (or B/C, which is fine)
- [ ] `make setup` → completes
- [ ] `.env` has your key → `make doctor` shows PASS on the key row
- [ ] `make cluster` → ALL PASS
- [ ] `make tour` → you've seen the cluster
- [ ] `make lab1 ...` → RB-014 comes back
- [ ] `make clean` → tidy until the morning

Nothing here expires. If tonight isn't the night, it'll behave identically next
month.
