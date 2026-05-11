import pytest

from backend.answering.models.answer import (
    AnswerCitation,
    AnswerConfidence,
    GroundedAnswer,
    HallucinationCheck,
)


@pytest.fixture
def good_answer() -> GroundedAnswer:
    """A high-quality, cacheable answer."""
    return GroundedAnswer(
        query="What is MCA eligibility?",
        answer="Eligibility for MCA requires a relevant bachelor degree [1].",
        citations=[
            AnswerCitation(
                index=1,
                chunk_id="c1",
                source_url="https://mitaoe.ac.in/mca",
                title="MCA Admissions",
                section_path=["Admissions", "Eligibility"],
            )
        ],
        confidence=AnswerConfidence(
            answer_confidence=0.78,
            grounding_confidence=0.65,
            hallucination_risk=0.05,
            citation_coverage=0.5,
            rerank_confidence=0.7,
        ),
        hallucination=HallucinationCheck(
            hallucination_risk=0.05,
            safe_to_return=True,
            judge_used=True,
        ),
        abstained=False,
        used_chunks=["c1"],
        provider="mock",
        model="mock-grounded",
    )


@pytest.fixture
def abstained_answer() -> GroundedAnswer:
    return GroundedAnswer(
        query="Out of scope",
        answer="I could not find reliable information about that in the MITAOE data.",
        citations=[],
        confidence=AnswerConfidence(grounding_confidence=0.0),
        abstained=True,
        abstention_reason="no_context_blocks",
        provider="mock",
        model="mock-grounded",
    )
