"""The RB-009 / RB-014 pair is the single most load-bearing artefact in this
repo. It is the live demo in Segment 7 and the trap case in the eval harness.

It is also the easiest thing here to break by accident: adding a sentence to
either runbook shifts BM25 scores, and the failure is silent — retrieval still
returns something plausible, the demo just stops making its point.

So it is a test, not a hand-check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "labs" / "lab1-knowledge-layer"))

from retrieval import load_corpus, search  # noqa: E402

PROD_CRASHLOOP_Q = "why are prod inference pods repeatedly restarting?"


def test_the_eval_trap_uses_the_question_this_file_tunes():
    """Single source of truth for the trap question.

    These drifted once already: cases.yaml asked "why are the model-serving pods
    in ml-prod repeatedly restarting?" while this file tuned against "why are
    prod inference pods repeatedly restarting?". Different wording, different
    BM25 ranking — RB-014 won the eval question, case-08 passed when it was
    designed to fail, and every assertion in this file was still green. The
    trap was broken and nothing said so.
    """
    import yaml
    cases = yaml.safe_load((REPO / "labs" / "lab4-evals" / "cases.yaml").read_text())["cases"]
    trap = next(c for c in cases if c.get("expect_fail"))
    assert trap["question"] == PROD_CRASHLOOP_Q, (
        "the eval trap question has drifted from the one this file tunes the "
        "RB-009/RB-014 pair against — retune the pair or restore the question"
    )


@pytest.fixture(scope="module")
def corpus():
    return load_corpus()


def test_corpus_size_and_frontmatter(corpus):
    assert len(corpus) == 14
    for book in corpus:
        assert book.id.startswith("RB-"), book.path.name
        for required in ("id", "title", "environment", "namespace", "last_reviewed"):
            assert required in book.meta, f"{book.path.name} missing '{required}'"


def test_the_pair_exists_and_is_near_duplicate(corpus):
    """Same title, different environment, different remediation. If these ever
    diverge in title, the pair stops being a near-duplicate and the trap stops
    being convincing."""
    by_id = {b.id: b for b in corpus}
    rb009, rb014 = by_id["RB-009"], by_id["RB-014"]

    assert rb009.title == rb014.title
    assert rb009.environment == "staging"
    assert rb014.environment == "prod"
    assert rb014.meta.get("supersedes") == "RB-009"

    # The remediations must be materially different, not differently worded.
    assert "delete configmap model-config" in rb009.body.lower()
    assert "do not delete the model configmap" in rb014.body.lower()
    assert "rollout undo" in rb014.body.lower()
    assert "rollout undo" not in rb009.body.lower()


def test_metadata_filter_returns_the_prod_runbook(corpus):
    """Criterion 16.5, first half."""
    hits = search(PROD_CRASHLOOP_Q, corpus, environment="prod", namespace="ml-prod")
    assert hits[0].runbook.id == "RB-014"
    assert all(h.runbook.environment == "prod" for h in hits)


def test_without_the_filter_the_staging_runbook_wins(corpus):
    """Criterion 16.5, second half — and the whole reason Lab 1 exists.

    Unfiltered, the lexically denser staging runbook outranks the correct prod
    one. The agent then confidently recommends deleting a ConfigMap that
    RB-014 explicitly says causes a production outage.
    """
    hits = search(PROD_CRASHLOOP_Q, corpus, use_metadata_filter=False)
    assert hits[0].runbook.id == "RB-009"
    assert hits[0].runbook.environment == "staging"


def test_the_two_commands_return_different_top_runbooks(corpus):
    """The contrast is the payload. If these ever agree, the lab is pointless."""
    filtered = search(PROD_CRASHLOOP_Q, corpus, environment="prod", namespace="ml-prod")
    unfiltered = search(PROD_CRASHLOOP_Q, corpus, use_metadata_filter=False)
    assert filtered[0].runbook.id != unfiltered[0].runbook.id


def test_trap_has_a_workable_margin(corpus):
    """Guard against the pair drifting to a coin-flip.

    A 1% margin would still pass the assertions above while being one
    reworded sentence away from flipping on stage.
    """
    hits = {h.runbook.id: h.score for h in search(
        PROD_CRASHLOOP_Q, corpus, use_metadata_filter=False, top_k=14)}
    margin = (hits["RB-009"] - hits["RB-014"]) / hits["RB-014"]
    assert margin > 0.10, f"RB-009 only beats RB-014 by {margin:.1%} — too fragile to demo"


@pytest.mark.parametrize(
    "question,expected,env,ns",
    [
        ("GPU pods stuck pending insufficient resources taint", "RB-002", "prod", "ml-prod"),
        ("which namespace hosts the inference service", "RB-005", "prod", "ml-prod"),
        ("inference latency spike after deployment cpu throttling", "RB-007", "prod", "ml-prod"),
        ("HPA configured but never scaling threshold", "RB-011", "prod", "ml-prod"),
        ("rollback a failed deployment bad image tag", "RB-012", "prod", "ml-prod"),
        ("configuration drift between prod and staging environments", "RB-003", "prod", "ml-prod"),
    ],
)
def test_each_scenario_retrieves_its_runbook(corpus, question, expected, env, ns):
    """Every scenario the session demos must actually retrieve its runbook.
    Distractors exist to make this non-trivial."""
    hits = search(question, corpus, environment=env, namespace=ns)
    assert hits[0].runbook.id == expected, \
        f"got {[h.runbook.id for h in hits]}, wanted {expected} first"


def test_filter_is_hard_not_soft(corpus):
    """A staging runbook must be *excluded* from a prod query, not merely
    ranked lower. Soft filtering can always be outweighed by lexical match —
    which is precisely the failure this filter prevents."""
    hits = search(PROD_CRASHLOOP_Q, corpus, environment="prod", top_k=14)
    assert "RB-009" not in {h.runbook.id for h in hits}
