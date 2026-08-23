#!/usr/bin/env python3
"""Lab 3 — guardrails for an agent that acts.

    make lab3                       # read-only. The agent proposes; it cannot act.
    make lab3 ARGS='--allow-writes' # the agent can act, behind the approval gate
    make lab3 ARGS='--rbac-demo'    # 30 seconds on why scoped credentials matter

Labs 1 and 2 built an agent that is right. This lab is about an agent that is
right and *also* cannot quietly take production down while being right.

Run it read-only first. Watch it propose a correct rollback and be refused.
Then run it with --allow-writes and watch it dry-run, present the diff, and
wait for you.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab1-knowledge-layer"))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab2-live-state-agent"))

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"

AGENT_KUBECONFIG = REPO_ROOT / "cluster" / "rbac" / "agent.kubeconfig"

QUESTION = (
    "The inference deployment in ml-prod is failing. Diagnose it, then use your "
    "tools to dry-run and propose the rollback."
)


def rbac_demo() -> int:
    """Show that the agent's credentials are enforced by the API server, not by us.

    This takes about thirty seconds live and it is the moment that lands the
    whole segment: every other guardrail in this repo is code we wrote and could
    have got wrong. This one is Kubernetes saying no.
    """
    if not AGENT_KUBECONFIG.exists():
        print(f"{YELLOW}No agent kubeconfig. Run `make cluster` first.{RESET}")
        return 1

    print(f"\n{BOLD}Who is the agent?{RESET}")
    subprocess.run(["kubectl", "--kubeconfig", str(AGENT_KUBECONFIG), "auth", "whoami"])

    checks = [
        ("list pods in ml-prod",     ["auth", "can-i", "list", "pods", "-n", "ml-prod"],     "yes"),
        ("list pods in ml-staging",  ["auth", "can-i", "list", "pods", "-n", "ml-staging"],  "yes"),
        ("patch deploy in ml-prod",  ["auth", "can-i", "patch", "deployments", "-n", "ml-prod"], "yes"),
        ("patch deploy in ml-staging", ["auth", "can-i", "patch", "deployments", "-n", "ml-staging"], "no"),
        ("read secrets in ml-prod",  ["auth", "can-i", "get", "secrets", "-n", "ml-prod"],   "no"),
        ("read pods in kube-system", ["auth", "can-i", "list", "pods", "-n", "kube-system"], "no"),
        ("delete anything in ml-prod", ["auth", "can-i", "delete", "deployments", "-n", "ml-prod"], "no"),
    ]

    print(f"\n{BOLD}What is it permitted to do?{RESET}")
    ok = True
    for label, args, expected in checks:
        proc = subprocess.run(
            ["kubectl", "--kubeconfig", str(AGENT_KUBECONFIG), *args],
            capture_output=True, text=True)
        got = proc.stdout.strip()
        matched = got == expected
        ok &= matched
        colour = GREEN if got == "yes" else RED
        mark = "" if matched else f"  {YELLOW}(expected {expected}){RESET}"
        print(f"  {label:<32} {colour}{got}{RESET}{mark}")

    print(f"\n{BOLD}And what happens when it tries anyway?{RESET}")
    proc = subprocess.run(
        ["kubectl", "--kubeconfig", str(AGENT_KUBECONFIG), "get", "pods", "-n", "kube-system"],
        capture_output=True, text=True)
    print(f"  {RED}{(proc.stderr or proc.stdout).strip()[:400]}{RESET}")

    print(f"\n{DIM}That refusal came from the Kubernetes API server, not from our code.")
    print("No prompt, no reasoning, and no amount of persuasion changes it. Every")
    print(f"other guardrail in this repo is something we wrote and could get wrong.{RESET}\n")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Lab 3 — guardrails")
    ap.add_argument("question", nargs="?", default=QUESTION)
    ap.add_argument("--allow-writes", action="store_true",
                    help="register the write tools. They still require approval.")
    ap.add_argument("--rbac-demo", action="store_true")
    ap.add_argument("--max-iterations", type=int, default=12)
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    args = ap.parse_args()

    if args.rbac_demo:
        return rbac_demo()

    from agent.guardrails import Guardrails, tool_definitions
    from agent.loop import WRITES_ENABLED_SYSTEM, investigate
    from agent.provider import NoCredentials
    from investigate import retrieve_context
    import asyncio

    guard = Guardrails(
        allow_writes=args.allow_writes,
        kubeconfig=str(AGENT_KUBECONFIG) if AGENT_KUBECONFIG.exists() else None,
    )

    banner = (f"{GREEN}WRITES ENABLED{RESET} — every write still stops at the approval gate"
              if args.allow_writes else
              f"{CYAN}READ-ONLY{RESET} — write tools are registered but will refuse")
    print(f"\n{BOLD}guardrails:{RESET} {banner}")
    print(f"{DIM}credentials: {'ml-prod/infra-agent ServiceAccount' if AGENT_KUBECONFIG.exists() else 'ambient kubeconfig (run make cluster for the scoped one)'}{RESET}")
    audit_start = len(guard.audit.entries())
    print(f"{DIM}audit log:   {guard.audit.path}{RESET}")
    print(f"{DIM}             tail it live:  tail -f {guard.audit.path.name}{RESET}")

    context = retrieve_context(args.question, environment="prod", namespace="ml-prod")

    try:
        result = asyncio.run(investigate(
            args.question,
            context=context,
            provider_name=args.provider,
            max_iterations=args.max_iterations,
            system_extra=WRITES_ENABLED_SYSTEM if args.allow_writes else "",
            extra_tools=tool_definitions(),
            tool_dispatch=guard.dispatch,
        ))
    except NoCredentials as e:
        print(f"\n{YELLOW}{e}{RESET}\n")
        return 1

    print(f"{BOLD}answer{RESET}\n")
    print(result.answer)

    # Only this run's entries. audit.jsonl is append-only, so replaying the
    # whole file meant a read-only session printed the "granted" line from an
    # earlier --allow-writes run — which on a screen share reads as if the
    # read-only agent just applied a change to production.
    written = [e for e in guard.audit.entries()[audit_start:] if e["approval"] != "n/a"]
    if written:
        print(f"\n{BOLD}audit trail — every gated decision{RESET}")
        for e in written[-10:]:
            colour = {"granted": GREEN, "denied": YELLOW,
                      "refused_read_only": RED, "not_required": DIM}.get(e["approval"], DIM)
            print(f"  {DIM}{e['timestamp']}{RESET}  {e['tool']:<22} "
                  f"{colour}{e['approval']}{RESET}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
