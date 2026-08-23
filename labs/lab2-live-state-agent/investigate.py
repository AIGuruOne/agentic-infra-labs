#!/usr/bin/env python3
"""Lab 2 — the agent meets the cluster.

    make lab2 ARGS='--scenario 1'
    make lab2 ARGS='"why are prod pods restarting?" --environment prod --namespace ml-prod'

Lab 1 gave the agent a knowledge layer. This adds the live-state layer: the same
runbooks, plus MCP tools over Kubernetes and Prometheus, plus a loop that lets
the model decide what to look at next.

The difference is the whole architecture. A chatbot retrieves and answers. This
retrieves, then goes and *checks*.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "labs" / "lab1-knowledge-layer"))

from retrieval import load_corpus, search  # noqa: E402

BOLD, DIM, RESET, YELLOW = "\033[1m", "\033[2m", "\033[0m", "\033[33m"

# The seven scenarios, each paired with the metadata that scopes retrieval.
SCENARIOS = {
    1: dict(question="Why are the model-serving pods in ml-prod repeatedly restarting?",
            environment="prod", namespace="ml-prod"),
    2: dict(question="How do I troubleshoot the GPU scheduling failure in ml-prod? "
                     "A pod is stuck Pending.",
            environment="prod", namespace="ml-prod"),
    3: dict(question="Which namespace actually hosts the production inference service?",
            environment="prod", namespace="ml-prod"),
    4: dict(question="Model latency in ml-prod has suddenly increased. What should I check?",
            environment="prod", namespace="ml-prod"),
    5: dict(question="Where is autoscaling configured for the ml-prod inference deployment, "
                     "and will it actually scale?",
            environment="prod", namespace="ml-prod"),
    6: dict(question="How is the sentiment model deployed across environments, and where do "
                     "prod and staging differ?",
            environment="prod", namespace="ml-prod"),
    7: dict(question="The ml-prod inference deployment is failing. What are the rollback steps?",
            environment="prod", namespace="ml-prod"),
}


def retrieve_context(question: str, *, environment=None, namespace=None,
                     use_filter=True, top_k=3, quiet=False) -> str:
    """Retrieve runbooks and format them as context for the agent.

    Note top_k=3 here where Lab 1 used 1. The agent has live cluster state to
    check a runbook against, so extra candidates are useful rather than
    dangerous — it can rule one out with evidence instead of guessing. That is
    itself a result worth pointing at: the live-state layer makes the retrieval
    layer safer, and it is why Lab 2 can afford a wider net than Lab 1.

    It also matters for recall. BM25 ranks "Model latency has suddenly
    increased" against the HPA runbook above the latency runbook, because the
    question shares more words with the former. At top_k=2 the correct runbook
    never reaches the agent at all.
    """
    corpus = load_corpus()
    hits = search(question, corpus, environment=environment, namespace=namespace,
                  use_metadata_filter=use_filter, top_k=top_k)
    if not quiet:
        mode = "filter ON" if use_filter else f"{YELLOW}filter OFF{RESET}"
        print(f"\n{BOLD}runbooks retrieved{RESET} {DIM}({mode}){RESET}")
        for h in hits:
            print(f"  {h.runbook.id}  score {h.score:5.2f}  "
                  f"{DIM}environment={h.runbook.environment}  {h.runbook.title}{RESET}")

    parts = ["Runbooks retrieved for this incident:\n"]
    for h in hits:
        m = h.runbook.meta
        header = (f"--- {h.runbook.id} (environment={m.get('environment')}, "
                  f"namespace={m.get('namespace')}, last_reviewed={m.get('last_reviewed')}) ---"
                  if use_filter else f"--- {h.runbook.id} ---")
        parts.append(f"\n{header}\n{h.runbook.body.strip()}\n")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Lab 2 — live-state agent")
    ap.add_argument("question", nargs="?", help="free-form question")
    ap.add_argument("--scenario", type=int, choices=sorted(SCENARIOS),
                    help="run one of the seven session scenarios")
    ap.add_argument("--environment")
    ap.add_argument("--namespace")
    ap.add_argument("--no-metadata-filter", action="store_true")
    ap.add_argument("--max-iterations", type=int, default=12)
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    args = ap.parse_args()

    if args.scenario:
        spec = SCENARIOS[args.scenario]
        question = spec["question"]
        environment = args.environment or spec["environment"]
        namespace = args.namespace or spec["namespace"]
        print(f"{DIM}scenario {args.scenario} — run 'make break-{args.scenario}' first "
              f"if you have not already{RESET}")
    elif args.question:
        question, environment, namespace = args.question, args.environment, args.namespace
    else:
        ap.error("give a question or --scenario N")

    context = retrieve_context(question, environment=environment, namespace=namespace,
                               use_filter=not args.no_metadata_filter)

    from agent.loop import run
    from agent.provider import NoCredentials

    try:
        result = run(question, context=context, provider_name=args.provider,
                     max_iterations=args.max_iterations)
    except NoCredentials as e:
        print(f"\n{YELLOW}{e}{RESET}\n")
        return 1

    print(f"{BOLD}answer{RESET}\n")
    print(result.answer)
    print(f"\n{DIM}{result.iterations} iterations · tools: "
          f"{', '.join(dict.fromkeys(result.tools_used)) or 'none'}{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
