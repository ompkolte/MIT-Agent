from __future__ import annotations

from backend.answering.models.answer import GroundedAnswer


# Pragmatic thresholds — see Phase 6.5 design notes. Real-world grounding scores in this
# corpus sit around 0.5-0.7 and the LLM cites 1-3 of 5-7 context blocks. Strict spec
# (grounding>=0.7, coverage==1.0) would leave the cache empty.
MIN_GROUNDING_CONFIDENCE = 0.5
MAX_HALLUCINATION_RISK = 0.3


def is_cacheable(answer: GroundedAnswer) -> tuple[bool, str | None]:
    """Decide whether an answer is safe to cache. Returns (eligible, reason_when_not).

    Rejecting an answer just means we run the full RAG path next time the same query
    arrives — there is no correctness cost, only a latency one.
    """
    if answer.abstained:
        return False, "abstained"
    if not answer.citations:
        return False, "no_citations"
    if answer.confidence.grounding_confidence < MIN_GROUNDING_CONFIDENCE:
        return False, f"low_grounding:{answer.confidence.grounding_confidence:.2f}"
    risk = answer.hallucination.hallucination_risk if answer.hallucination.judge_used else 0.0
    if risk > MAX_HALLUCINATION_RISK:
        return False, f"high_hallucination_risk:{risk:.2f}"
    return True, None


def is_hit_still_valid(answer: GroundedAnswer) -> tuple[bool, str | None]:
    """Re-validate a cached entry at lookup time. Catches the rare case where a stored
    answer's citations or confidence drifted relative to what we now accept (e.g. if the
    eligibility thresholds were raised after the entry was written)."""
    if answer.abstained:
        return False, "stored_was_abstention"
    if not answer.citations:
        return False, "stored_has_no_citations"
    if answer.confidence.grounding_confidence < MIN_GROUNDING_CONFIDENCE:
        return False, "stored_grounding_below_threshold"
    return True, None
