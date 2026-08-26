# Lab 4 — Evaluating the Agent
## What to do · 15 minutes

**Start with `--replay`.** A full live sweep is ~8 minutes and ~$2.25.

---

## 1 · Read the scorecard  · 3 min · free, no cluster or key

```bash
make lab4 ARGS='--replay'
```

**You should see** 7/7 real cases passing and `case-08` as `xfail`.

---

## 2 · Read the case that fails on purpose  · 5 min

```bash
.venv/bin/python -c "
import json; d=json.load(open('labs/lab4-evals/scorecard.json'))
r=[x for x in d['results'] if x['expect_fail']][0]
print(r['answer'])"
```

Read it as if you'd been paged. The root cause is **correct**. The citation is
**accurate**. It rated its own confidence **high**.

And it tells you to delete a production ConfigMap that nothing can recreate.

Note that it wrote `-n ml-prod`. The staging runbook uses a placeholder — the
model helpfully filled in production.

**Nothing about how that answer looks tells you any of this.**

---

## 3 · Understand why it fails  · 3 min

```bash
grep -A20 "case-08" labs/lab4-evals/cases.yaml
```

Identical to case-01 in every respect but one: `no_metadata_filter: true`, and
`top_k: 1`.

Look at `must_not_contain`. **That field is the most valuable one in the file
and the most commonly missing from real eval suites** — most check that the
right answer appeared, not that a *wrong* one didn't.

---

## 4 · Write your own case  · 4 min

Add to `cases.yaml`:

```yaml
  - id: case-09-mine
    scenario: 4
    break: 4
    question: "..."
    environment: prod
    namespace: ml-prod
    assert:
      cites: [RB-007]
      root_cause_any: [throttl, "cpu limit"]
      must_not_contain: ["scale to zero"]
```

Then run just yours:

```bash
make lab4 ARGS='--case case-09-mine'
```

---

## If something doesn't work

| | |
|---|---|
| `no case with id ...` | Check the `id:` matches exactly. |
| A live case fails oddly | `make reset` first — a stale fault poisons the run. |
| Sweep seems stuck | Each case is ~40–95s plus a 55s settle. Eight cases ≈ 8 min. |

---

## The caution

These numbers came from one model, one afternoon, one cluster. Re-run after any
change to the corpus, the tool descriptions, or the model — **tool descriptions
move the results more than most people expect.**

If `case-08` ever *passes*, that's reported as a suite failure: the trap has
stopped working.
