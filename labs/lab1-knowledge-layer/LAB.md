# Lab 1 — The Knowledge Layer
## What to do · 20 minutes

**You need:** Python. That's all. No Docker, no cluster, no API key for the
first three tasks.

**If you get lost:** every command here is also in `EXPECTED.md`, with the
output it should produce and why.

---

## 1 · Ask the question with the metadata  · 2 min

```bash
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --environment prod --namespace ml-prod'
```

**You should see** a ranked list of five runbooks, with `RB-014` first, and
`-> sent to model` beside it:

```
  1. RB-014  score  4.99  environment=prod   Model server crashloop...  -> sent to model
  2. RB-006  score  3.39  environment=prod   PersistentVolumeClaim...   (not sent)
```

Then a grounded answer that tells you to `rollout undo`, and warns you **not**
to delete the ConfigMap.

> **No API key?** Add `--retrieval-only`. You still get the ranking, which is
> the part this lab is about.

---

## 2 · Ask the same question without the metadata  · 2 min

```bash
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --no-metadata-filter'
```

**You should see** `RB-009` first — and `environment=staging` highlighted.

**Read the answer properly.** It tells you to delete the model ConfigMap, and
then, if that doesn't help, delete the Deployment. In production.

### The thing to sit with

Same corpus. Same ranker. Same question. Nothing failed. RB-009 is shorter and
uses more of the question's words, and BM25 rewards both.

Now open the two runbooks and search them for the word "staging":

```bash
grep -n "staging" runbooks/RB-009-model-server-crashloop-staging.md
```

**The body never says it.** Only the frontmatter does — and task 2 threw the
frontmatter away.

---

## 3 · Watch a good model rescue a bad retrieval  · 4 min

```bash
make lab1 ARGS='"why are prod inference pods repeatedly restarting?" --no-metadata-filter --top-k 3'
```

Now three runbooks reach the model instead of one — so RB-014 comes along too,
ranked second.

**You should see** the answer come out *correct*, despite the ranking being
wrong. The model reads RB-014's "do not delete the ConfigMap in production"
warning and works out which document applies.

### The question worth asking yourself

That's reassuring. But **how would you have known it happened?**

Both answers look identical from the outside — same format, same confidence,
same citation style. If your pipeline is quietly relying on the model to repair
your retrieval, you have no way to measure it.

*(That is what Lab 4 exists for. Hold the thought.)*

---

## 4 · Prove RB-009 isn't a bad runbook  · 2 min

```bash
make lab1 ARGS='"why are staging inference pods repeatedly restarting?" --environment staging --namespace ml-staging'
```

**You should see** RB-009 as the top hit — and now it's the *right* answer.
Deleting a ConfigMap in staging is fine; the pipeline regenerates it.

**RB-009 was never a bad runbook. It was a bad match.**

> **Why is the score negative (−2.10)?** BM25 scores aren't probabilities and
> they aren't bounded at zero. A term that appears in almost every document gets
> a negative weight — it's evidence *against* the document being distinctive.
> With only one candidate left after filtering, the absolute number stops
> meaning anything. **Only the ordering matters, and only within one query.**

---

## 5 · Try to break it  · 5 min

> **Note the `--retrieval-only` on two of these.** That flag skips the LLM call
> on purpose — those two are about *which runbooks survive the filter*, so the
> ranking is the whole answer and a written response would only get in the way.
>
> The Kafka one has no such flag, so it does call the model. **If you get a
> ranking but no prose on the last two, nothing is wrong.** Drop
> `--retrieval-only` from either and you'll get an answer too.

Pick any of these:

```bash
# a question the corpus does not cover — does it decline, or invent?
make lab1 ARGS='"why is my Kafka consumer lagging?" --environment prod'

# filter on a GPU type no runbook declares — what survives, and why?
make lab1 ARGS='"pods restarting" --environment prod --gpu-type h100 --retrieval-only'

# every metadata axis at once
make lab1 ARGS='"pods restarting" --environment prod --cluster ml-cluster-1 --namespace ml-prod --service inference-api --model sentiment-v2 --cloud-provider aws --region us-east-1 --retrieval-only'
```

### The `--gpu-type h100` one has a lesson in it

You get results back — RB-001, RB-006, RB-008 — even though no runbook mentions
an H100.

Look at their frontmatter: `gpu_type: null`. **Null means "applies regardless"**,
so those runbooks survive a GPU filter on purpose. Most runbooks aren't
GPU-specific, and excluding them from a GPU query would be worse than not
filtering at all.

That's a design decision you'd have to make in your own corpus, and it's the
kind of thing that only shows up when you try to break the filter.

---

## If something doesn't work

| | |
|---|---|
| `make: *** No rule to make target` | You're in the wrong directory. `cd` to the repo root. |
| `ModuleNotFoundError` | Run `make setup`. |
| `NoCredentials` / no answer, just a ranking | Expected without an API key. Add `--retrieval-only`, or put your key in `.env`. |
| Scores differ from `EXPECTED.md` | They shouldn't — BM25 is deterministic. Check you haven't edited the runbooks. |
| Answer differs from `EXPECTED.md` | Expected. The model is non-deterministic. The **runbook it follows** should match; the prose won't. |

---

## Done early?

Open `runbooks/RB-014-model-server-crashloop-prod.md` and read the frontmatter.
Eight fields. **Which of them would your own runbooks have today?**

That schema is the thing to take home — more than any code in this repo.

---

## Not running anything?

`EXPECTED.md` in this folder has every command above with its real captured
output and the reasoning written out. You can do this entire lab by reading.
