#!/usr/bin/env python3
"""Lab 4 — evaluating the agent.

    make lab4 ARGS='--replay'            # instant, from the committed scorecard
    make lab4 ARGS='--case case-08-...'  # one case, live
    make lab4                            # full sweep. Minutes. Not on camera.

An agent that runs is not an agent that works. This measures whether it is
*right*, which is a different question and the only one that matters once it is
allowed to touch production.

Deliberately thin. This is demo-quality, not framework-quality: it injects a
fault, asks the question, checks the answer against coarse assertions, resets,
and moves on. Scoring prose precisely is a research problem. Scoring whether the
agent reached the right runbook and named the right cause takes an afternoon and
catches the failures that matter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab1-knowledge-layer"))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab2-live-state-agent"))

CASES = Path(__file__).parent / "cases.yaml"
SCORECARD = Path(__file__).parent / "scorecard.json"

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, RED, YELLOW, CYAN = "\033[32m", "\033[31m", "\033[33m", "\033[36m"


def _run(script: str) -> bool:
    """Run a fault script. Report failure; never abort the sweep.

    reset.sh ends with `exec verify.sh`, which exits non-zero if any health row
    FAILs — including "Prometheus has stub metrics", which verify itself
    annotates as "scrape takes ~30s" while reset sleeps only 15. With
    check=True one such blip anywhere in an eight-case run raised
    CalledProcessError, and because the scorecard is only written after every
    case completes, it discarded the whole sweep: minutes of wall-clock and
    real API spend, thrown away by a transient scrape timing.
    """
    proc = subprocess.run([str(REPO_ROOT / script)],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        print(f"  {YELLOW}warning: {script} exited {proc.returncode} — continuing{RESET}")
        return False
    return True


def grade(answer: str, spec: dict) -> tuple[bool, list[str]]:
    """Score one answer. Returns (passed, list of failure reasons).

    Case-insensitive substring matching throughout. Crude on purpose — the
    alternative is an LLM judge, which introduces the exact failure mode we are
    trying to measure into the thing doing the measuring.
    """
    low = answer.lower()
    failures: list[str] = []

    for rb in spec.get("cites", []):
        if rb.lower() not in low:
            failures.append(f"did not cite {rb}")

    any_of = spec.get("root_cause_any", [])
    if any_of and not any(str(k).lower() in low for k in any_of):
        failures.append(f"root cause missing any of {any_of}")

    for k in spec.get("root_cause_all", []):
        if str(k).lower() not in low:
            failures.append(f"root cause missing {k!r}")

    rem = spec.get("remediation_any", [])
    if rem and not any(str(k).lower() in low for k in rem):
        failures.append(f"remediation missing any of {rem}")

    for banned in spec.get("must_not_contain", []):
        if str(banned).lower() in low:
            failures.append(f"recommended a forbidden action: {banned!r}")

    return not failures, failures


async def run_case(case: dict, *, provider: str, settle: int) -> dict:
    from agent.loop import investigate
    from investigate import retrieve_context

    print(f"\n{BOLD}{case['id']}{RESET} {DIM}(break-{case['break']}){RESET}")
    _run("faults/reset.sh")
    _run(f"faults/break-{case['break']}.sh")
    time.sleep(settle)

    use_filter = not case.get("no_metadata_filter", False)
    context = retrieve_context(
        case["question"],
        environment=case.get("environment"), namespace=case.get("namespace"),
        use_filter=use_filter, top_k=case.get("top_k", 3), quiet=True,
    )

    started = time.time()
    result = await investigate(case["question"], context=context,
                               provider_name=provider, quiet=True)
    passed, failures = grade(result.answer, case["assert"])
    expected_fail = case.get("expect_fail", False)

    # An expected failure that passes is itself a problem: the trap has stopped
    # working and there is no demo. Both mismatches are surfaced.
    if expected_fail:
        status = "xfail" if not passed else "unexpected-pass"
    else:
        status = "pass" if passed else "fail"

    colour = {"pass": GREEN, "xfail": YELLOW, "fail": RED, "unexpected-pass": RED}[status]
    print(f"  {colour}{status.upper()}{RESET}  {DIM}{result.iterations} iterations, "
          f"{time.time() - started:.0f}s, tools: {', '.join(dict.fromkeys(result.tools_used))}{RESET}")
    for f in failures:
        print(f"    {DIM}- {f}{RESET}")

    return {
        "id": case["id"], "status": status, "passed": passed,
        "expect_fail": expected_fail, "failures": failures,
        "iterations": result.iterations,
        "tools_used": list(dict.fromkeys(result.tools_used)),
        "duration_seconds": round(time.time() - started, 1),
        "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "answer": result.answer,
    }


def scorecard(results: list[dict]) -> int:
    print(f"\n{BOLD}scorecard{RESET}\n")
    print(f"  {'case':<32} {'status':<16} {'iters':>5}  {'sec':>5}  tools")
    print(f"  {'-' * 32} {'-' * 16} {'-' * 5}  {'-' * 5}  {'-' * 5}")
    for r in results:
        colour = {"pass": GREEN, "xfail": YELLOW, "fail": RED, "unexpected-pass": RED}[r["status"]]
        print(f"  {r['id']:<32} {colour}{r['status']:<16}{RESET} {r['iterations']:>5}  "
              f"{r['duration_seconds']:>5.0f}  {DIM}{len(r['tools_used'])} distinct{RESET}")

    passed = sum(r["status"] == "pass" for r in results)
    xfail = sum(r["status"] == "xfail" for r in results)
    bad = [r for r in results if r["status"] in ("fail", "unexpected-pass")]
    real = [r for r in results if not r["expect_fail"]]

    print(f"\n  {passed}/{len(real)} real cases passed"
          + (f", {xfail} expected failure(s) behaved as designed" if xfail else ""))

    trap = next((r for r in results if r["expect_fail"]), None)
    if trap and trap["status"] == "xfail":
        print(f"\n  {YELLOW}{BOLD}case-08 failed, as it is designed to.{RESET}")
        print(f"  {DIM}Read its answer in the scorecard JSON. It is fluent, correctly")
        print("  formatted, properly cited — and it recommends deleting a production")
        print(f"  ConfigMap. Nothing in its presentation signals that it is wrong.{RESET}")
    elif trap:
        print(f"\n  {RED}{BOLD}case-08 PASSED, which means the trap has stopped working.{RESET}")
        print(f"  {DIM}Check tests/test_retrieval.py — the RB-009/RB-014 pair has drifted.{RESET}")

    print()
    return 1 if bad else 0


def replay() -> int:
    if not SCORECARD.exists():
        print(f"{YELLOW}No committed scorecard at {SCORECARD}. Run a full sweep first.{RESET}")
        return 1
    data = json.loads(SCORECARD.read_text())
    print(f"{DIM}replaying scorecard recorded {data['recorded_at']} "
          f"on {data['provider']}/{data['model']}{RESET}")
    return scorecard(data["results"])


def main() -> int:
    ap = argparse.ArgumentParser(description="Lab 4 — eval harness")
    ap.add_argument("--replay", action="store_true",
                    help="print the committed scorecard instead of running. Use this live.")
    ap.add_argument("--case", help="run a single case by id")
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--settle", type=int, default=40,
                    help="seconds to wait after injecting a fault before asking")
    ap.add_argument("--save", action="store_true", help="write scorecard.json")
    args = ap.parse_args()

    if args.replay:
        return replay()

    cases = yaml.safe_load(CASES.read_text())["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"{RED}no case with id {args.case!r}{RESET}")
            return 1

    print(f"{DIM}Running {len(cases)} case(s) live. A full sweep takes minutes —")
    print(f"use --replay on camera.{RESET}")

    from agent.provider import get_provider
    model = get_provider(args.provider).model

    def persist(rs):
        SCORECARD.write_text(json.dumps({
            "recorded_at": time.strftime("%Y-%m-%d %H:%M:%S%z"),
            "provider": args.provider, "model": model, "results": rs,
        }, indent=2) + "\n")

    results = []
    for c in cases:
        try:
            results.append(asyncio.run(run_case(c, provider=args.provider, settle=args.settle)))
        except Exception as e:                       # noqa: BLE001
            print(f"  {RED}ERROR{RESET} {c['id']} raised {type(e).__name__}: {e}")
            results.append({
                "id": c["id"], "status": "fail", "passed": False,
                "expect_fail": c.get("expect_fail", False),
                "failures": [f"harness error: {type(e).__name__}: {e}"],
                "iterations": 0, "tools_used": [], "duration_seconds": 0.0,
                "input_tokens": 0, "output_tokens": 0, "answer": "",
            })
        # Persist after every case. A sweep is minutes of wall-clock and real
        # API spend; losing all of it to the last case failing is not a
        # trade-off worth making.
        if args.save:
            persist(results)

    code = scorecard(results)
    if args.save:
        print(f"{DIM}wrote {SCORECARD}{RESET}\n")

    _run("faults/reset.sh")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
