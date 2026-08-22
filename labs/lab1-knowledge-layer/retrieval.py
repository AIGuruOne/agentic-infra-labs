"""The knowledge layer: BM25 over runbook bodies, with a hard pre-filter on
frontmatter metadata.

This is the hybrid. Not lexical-plus-dense — lexical-plus-structured. Two
retrievers with different failure modes, composed so that one covers the
other's blind spot:

  - BM25 is good at "which document is about this symptom" and completely blind
    to which environment the document applies to. Two runbooks describing the
    same crashloop score almost identically no matter which cluster they are
    written for.
  - The metadata filter knows nothing about the question's meaning, but it
    knows a prod incident cannot be answered by a staging runbook.

Neither is sufficient. A dense retriever would not help here: swapping BM25 for
embeddings changes which near-identical document wins by a few points of cosine
similarity, and changes nothing about the fact that the wrong environment's
document is still in the candidate set. The filter is what makes retrieval
correct; the ranker only decides the order.

That is the lesson Lab 1 exists to make visible, which is why `--no-metadata-filter`
is a first-class flag and not a debug option.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rank_bm25 import BM25Okapi

RUNBOOK_DIR = Path(__file__).resolve().parents[2] / "runbooks"

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass
class Runbook:
    id: str
    title: str
    path: Path
    body: str
    meta: dict = field(default_factory=dict)

    @property
    def environment(self) -> str | None:
        return self.meta.get("environment")

    @property
    def namespace(self) -> str | None:
        return self.meta.get("namespace")

    def tokens(self) -> list[str]:
        return _TOKEN.findall(f"{self.title} {self.body}".lower())


def load_corpus(directory: Path = RUNBOOK_DIR) -> list[Runbook]:
    """Parse every runbook's YAML frontmatter and body."""
    books: list[Runbook] = []
    for path in sorted(directory.glob("RB-*.md")):
        raw = path.read_text(encoding="utf-8")
        match = _FRONTMATTER.match(raw)
        if not match:
            raise ValueError(f"{path.name}: missing YAML frontmatter")
        meta = yaml.safe_load(match.group(1)) or {}
        books.append(
            Runbook(
                id=str(meta.get("id", path.stem)),
                title=str(meta.get("title", path.stem)),
                path=path,
                body=match.group(2),
                meta=meta,
            )
        )
    return books


def apply_metadata_filter(
    corpus: list[Runbook],
    environment: str | None = None,
    namespace: str | None = None,
    service: str | None = None,
) -> list[Runbook]:
    """Hard pre-filter. A runbook that does not apply is not ranked lower —
    it is not a candidate at all.

    Soft-filtering (boosting the right environment instead of excluding the
    wrong one) is the tempting version and the wrong one: a boost can always be
    outweighed by a strong enough lexical match, which is exactly the case this
    filter exists to prevent.
    """
    out = corpus
    if environment:
        out = [b for b in out if b.environment in (environment, None)]
    if namespace:
        out = [b for b in out if b.namespace in (namespace, None)]
    if service:
        out = [b for b in out if b.meta.get("service") in (service, None)]
    return out


@dataclass
class Hit:
    runbook: Runbook
    score: float


def search(
    query: str,
    corpus: list[Runbook] | None = None,
    *,
    environment: str | None = None,
    namespace: str | None = None,
    service: str | None = None,
    use_metadata_filter: bool = True,
    top_k: int = 3,
) -> list[Hit]:
    """Retrieve runbooks for a query.

    With `use_metadata_filter=False` the metadata is parsed and ignored — the
    same corpus, the same ranker, the filter simply not applied. That is what
    makes the two commands in the lab a controlled comparison rather than two
    different systems.
    """
    corpus = corpus if corpus is not None else load_corpus()
    candidates = (
        apply_metadata_filter(corpus, environment, namespace, service)
        if use_metadata_filter
        else corpus
    )
    if not candidates:
        return []

    bm25 = BM25Okapi([b.tokens() for b in candidates])
    scores = bm25.get_scores(_TOKEN.findall(query.lower()))
    ranked = sorted(zip(candidates, scores), key=lambda p: p[1], reverse=True)
    return [Hit(runbook=b, score=float(s)) for b, s in ranked[:top_k]]
