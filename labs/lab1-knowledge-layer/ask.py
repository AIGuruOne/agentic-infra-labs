#!/usr/bin/env python3
"""Lab 1 — the knowledge layer.

    ask.py "why are prod inference pods restarting?" --environment prod --namespace ml-prod
    ask.py "why are prod inference pods restarting?" --no-metadata-filter

Run those two commands back to back. Same corpus, same ranker, same question.
Different runbook, and a remediation that would cause an outage if you followed
the second one in production.

Retrieval runs without an API key. Only the grounded answer needs one.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from retrieval import Hit, load_corpus, search  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
YELLOW, CYAN = "\033[33m", "\033[36m"

SYSTEM = """You are an infrastructure assistant answering from a runbook corpus.

Rules:
- Answer ONLY from the runbooks provided. If they do not cover the question,
  say so rather than reasoning from general Kubernetes knowledge.
- Cite the runbook ID inline for every claim, like [RB-014].
- Lead with the remediation. The person reading this is in an incident.
- Give the concrete commands from the runbook, not a paraphrase.
- If a runbook explicitly warns against an action, carry that warning through.
"""


def render_hits(hits: list[Hit], *, filtered: bool, context_k: int) -> None:
    """Show the whole ranking and mark the context cutoff.

    Ranking and context are different numbers: this pipeline ranks the corpus
    and passes only the top `context_k` runbooks to the model, which is what
    most production RAG does. Printing both, with the cutoff visible, means
    nobody has to take our word for which document actually produced the
    answer.
    """
    mode = "metadata filter ON" if filtered else f"{YELLOW}metadata filter OFF{RESET}"
    print(f"\n{BOLD}ranked{RESET} {DIM}({mode}){RESET}")
    if not hits:
        print(f"  {DIM}no candidates matched the metadata filter{RESET}")
        return
    for i, h in enumerate(hits, 1):
        env = h.runbook.environment or "-"
        in_context = i <= context_k
        marker = f"{CYAN}-> sent to model{RESET}" if in_context else f"{DIM}(not sent){RESET}"
        colour = YELLOW if not filtered and env != "prod" else ""
        print(
            f"  {i}. {BOLD}{h.runbook.id}{RESET}  score {h.score:5.2f}  "
            f"{colour}environment={env:<8}{RESET} {DIM}{h.runbook.title:<48}{RESET} {marker}"
        )


def build_prompt(question: str, hits: list[Hit], *, metadata_aware: bool) -> str:
    """Build the generation prompt.

    When the metadata filter is off, the metadata is withheld from the prompt
    too. This is not us stacking the deck — it is what a metadata-blind
    pipeline actually looks like. A system that does not filter on environment
    is, in practice, a system that indexed the body text and threw the
    frontmatter away; it has nothing to put in the prompt.

    It also matters for the demo. Hand a good model the staging runbook clearly
    labelled `environment: staging` and it will notice, discount it, and answer
    correctly — the retrieval error gets silently repaired at generation time
    and the lesson evaporates. The failure this lab teaches is what happens
    when the environment is simply not knowable from what retrieval returned.
    """
    parts = [f"Question: {question}\n", "Runbooks retrieved for this question:\n"]
    for h in hits:
        m = h.runbook.meta
        if metadata_aware:
            header = (f"--- {h.runbook.id} (environment={m.get('environment')}, "
                      f"namespace={m.get('namespace')}, last_reviewed={m.get('last_reviewed')}) ---")
        else:
            header = f"--- {h.runbook.id} ---"
        parts.append(f"\n{header}\n{h.runbook.body.strip()}\n")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Lab 1 — metadata-filtered runbook retrieval")
    ap.add_argument("question")
    # One flag per filterable frontmatter field. Each is an axis along which a
    # lexically perfect match can still be the wrong document.
    ap.add_argument("--environment", help="prod | staging | dev")
    ap.add_argument("--cluster")
    ap.add_argument("--namespace")
    ap.add_argument("--service")
    ap.add_argument("--model")
    ap.add_argument("--gpu-type", dest="gpu_type")
    ap.add_argument("--provider")
    ap.add_argument("--region")
    ap.add_argument(
        "--no-metadata-filter",
        action="store_true",
        help="rank the whole corpus, ignoring environment/namespace. This is the lesson.",
    )
    ap.add_argument("--rank-k", type=int, default=5,
                    help="how many runbooks to rank and display")
    ap.add_argument("--top-k", type=int, default=1,
                    help="how many of the ranked runbooks are passed to the model as context")
    ap.add_argument("--retrieval-only", action="store_true", help="skip the LLM answer")
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    args = ap.parse_args()

    use_filter = not args.no_metadata_filter
    corpus = load_corpus()
    from retrieval import FILTERABLE_FIELDS
    constraints = {f: getattr(args, f, None) for f in FILTERABLE_FIELDS}
    hits = search(
        args.question, corpus,
        use_metadata_filter=use_filter, top_k=args.rank_k, **constraints,
    )

    print(f"\n{BOLD}question{RESET} {args.question}")
    print(f"{DIM}corpus: {len(corpus)} runbooks{RESET}")
    render_hits(hits, filtered=use_filter, context_k=args.top_k)
    context = hits[: args.top_k]

    if args.retrieval_only or not hits:
        print()
        return 0

    from agent.provider import NoCredentials, get_provider

    try:
        provider = get_provider(args.provider)
    except NoCredentials as e:
        print(f"\n{DIM}(no grounded answer: {e}){RESET}")
        print(f"{DIM} retrieval above still shows the whole point of this lab.{RESET}\n")
        return 0

    print(f"\n{BOLD}grounded answer{RESET} {DIM}({provider.name}/{provider.model}){RESET}\n")
    reply = provider.complete(
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(args.question, context, metadata_aware=use_filter)}],
    )
    print(reply.text.strip())
    print(f"\n{DIM}tokens: {reply.input_tokens} in / {reply.output_tokens} out{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
