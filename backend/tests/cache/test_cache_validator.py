from backend.cache.cache_validator import is_cacheable
from backend.answering.models.answer import AnswerConfidence, HallucinationCheck


def test_good_answer_is_cacheable(good_answer) -> None:
    ok, reason = is_cacheable(good_answer)
    assert ok is True
    assert reason is None


def test_abstention_is_not_cacheable(abstained_answer) -> None:
    ok, reason = is_cacheable(abstained_answer)
    assert ok is False
    assert reason == "abstained"


def test_no_citations_is_not_cacheable(good_answer) -> None:
    good_answer.citations = []
    ok, reason = is_cacheable(good_answer)
    assert ok is False
    assert reason == "no_citations"


def test_low_grounding_is_not_cacheable(good_answer) -> None:
    good_answer.confidence = AnswerConfidence(grounding_confidence=0.3)
    ok, reason = is_cacheable(good_answer)
    assert ok is False
    assert reason.startswith("low_grounding")


def test_high_hallucination_risk_is_not_cacheable(good_answer) -> None:
    good_answer.hallucination = HallucinationCheck(
        hallucination_risk=0.6, safe_to_return=False, judge_used=True
    )
    ok, reason = is_cacheable(good_answer)
    assert ok is False
    assert reason.startswith("high_hallucination_risk")


def test_judge_not_run_treated_as_zero_risk(good_answer) -> None:
    good_answer.hallucination = HallucinationCheck(judge_used=False)
    ok, _ = is_cacheable(good_answer)
    assert ok is True
