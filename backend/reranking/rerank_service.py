from __future__ import annotations

from typing import Protocol

from backend.reranking.aggregator_boost import boost_score
from backend.reranking.answerability import compute_answerability_score
from backend.reranking.duplicate_suppressor import suppress_semantic_duplicates
from backend.reranking.score_calibrator import calibrate, combine_relevance
from backend.reranking.semantic_diversity import diversity_rejection_reason
from backend.reranking.validators import RerankedChunk
from backend.retrieval.models.search import RetrievedChunk


class _RerankerLike(Protocol):
    def score(self, query: str, passages: list[str], batch_size: int = ...) -> "list":  # numpy.ndarray
        ...


class RerankService:
    """Orchestrates the rerank pipeline:
    cross-encoder score → sigmoid calibration → answerability → final blend
    → duplicate suppression → semantic diversity caps.

    Returns a tuple (kept, rejected): kept is the final top-K with rank 1..K; rejected
    carries the rest, each annotated with rejection_reason for inspector display.
    """

    def __init__(self, model: _RerankerLike) -> None:
        self.model = model

    def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
        top_k: int = 5,
        rerank_weight: float = 0.8,
        answerability_weight: float = 0.2,
        max_per_section_type: int = 2,
        max_per_document: int = 2,
        duplicate_threshold: int = 85,
    ) -> tuple[list[RerankedChunk], list[RerankedChunk]]:
        if not candidates:
            return [], []

        passages = [c.text for c in candidates]
        raw_scores = self.model.score(query, passages)

        scored: list[dict] = []
        for i, candidate in enumerate(candidates):
            raw = float(raw_scores[i])
            calibrated = calibrate(raw)
            # Aggregator pages (e.g. /student-clubs.php) get a small boost so the
            # comprehensive listing chunk survives the top-K cutoff even when the
            # cross-encoder ranks it mid-pack for list-style queries.
            calibrated_boosted = boost_score(calibrated, candidate.url, candidate.text)
            answerability = compute_answerability_score(candidate.text, candidate.token_count)
            final = combine_relevance(
                calibrated_boosted, answerability,
                rerank_weight=rerank_weight,
                answerability_weight=answerability_weight,
            )
            scored.append(
                {
                    "candidate": candidate,
                    "raw": raw,
                    "calibrated": calibrated_boosted,
                    "answerability": answerability,
                    "final": final,
                }
            )
        scored.sort(key=lambda s: s["final"], reverse=True)

        dedup_decisions = suppress_semantic_duplicates(
            [{"chunk_id": s["candidate"].chunk_id, "text": s["candidate"].text} for s in scored],
            similarity_threshold=duplicate_threshold,
        )

        section_counts: dict[str, int] = {}
        document_counts: dict[str, int] = {}
        kept: list[RerankedChunk] = []
        rejected: list[RerankedChunk] = []

        for i, scored_item in enumerate(scored):
            candidate = scored_item["candidate"]
            duplicate_of = dedup_decisions[i]
            rejection_reason: str | None = None
            diversity_kept = True

            if duplicate_of is not None:
                rejection_reason = f"duplicate_of:{duplicate_of}"
                diversity_kept = False
            elif len(kept) < top_k:
                diversity_reason = diversity_rejection_reason(
                    section_type=candidate.section_type,
                    document_id=candidate.document_id,
                    section_counts=section_counts,
                    document_counts=document_counts,
                    max_per_section_type=max_per_section_type,
                    max_per_document=max_per_document,
                )
                if diversity_reason is not None:
                    rejection_reason = diversity_reason
                    diversity_kept = False

            if rejection_reason is None and len(kept) < top_k:
                section_counts[candidate.section_type] = section_counts.get(candidate.section_type, 0) + 1
                document_counts[candidate.document_id] = document_counts.get(candidate.document_id, 0) + 1
                new_rank = len(kept) + 1
                kept.append(
                    self._build_reranked(
                        candidate, scored_item, duplicate_of, diversity_kept=True,
                        rejection_reason=None, rank=new_rank,
                    )
                )
            else:
                if rejection_reason is None and len(kept) >= top_k:
                    rejection_reason = "below_top_k"
                rejected.append(
                    self._build_reranked(
                        candidate, scored_item, duplicate_of, diversity_kept=False,
                        rejection_reason=rejection_reason, rank=0,
                    )
                )

        return kept, rejected

    @staticmethod
    def _build_reranked(
        candidate: RetrievedChunk,
        scored_item: dict,
        duplicate_of: str | None,
        *,
        diversity_kept: bool,
        rejection_reason: str | None,
        rank: int,
    ) -> RerankedChunk:
        return RerankedChunk(
            **candidate.model_dump(),
            rerank_score_raw=round(scored_item["raw"], 4),
            rerank_score=scored_item["calibrated"],
            answerability_score=scored_item["answerability"],
            final_relevance=scored_item["final"],
            duplicate_of=duplicate_of,
            diversity_kept=diversity_kept,
            rejection_reason=rejection_reason,
        ).model_copy(update={"rank": rank if rank else candidate.rank, "score": scored_item["final"]})
