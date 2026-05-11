from __future__ import annotations

from backend.answering.abstention import should_abstain
from backend.answering.answer_generator import generate_answer
from backend.answering.answer_validator import validate_answer
from backend.answering.citation_formatter import build_citations
from backend.answering.confidence import compute_answer_confidence
from backend.answering.hallucination_guard import validate_grounded_answer
from backend.answering.models.answer import (
    ABSTENTION_TEXT,
    AnswerConfidence,
    GroundedAnswer,
    HallucinationCheck,
    TokenUsage,
)
from backend.context.validators import GroundedContext
from backend.llm.provider_interface import BaseLLMProvider


class GroundedAnsweringService:
    """End-to-end grounded answering: abstain check → LLM generate → citation extract →
    answer validate → LLM-as-judge hallucination check → confidence aggregate."""

    def __init__(
        self,
        provider: BaseLLMProvider,
        model: str = "",
        judge_provider: BaseLLMProvider | None = None,
        judge_model: str = "",
        run_judge: bool = True,
    ) -> None:
        self.provider = provider
        self.model = model
        self.judge_provider = judge_provider or provider
        self.judge_model = judge_model
        self.run_judge = run_judge

    def answer(
        self,
        query: str,
        grounded_context: GroundedContext,
        rewritten_query: str | None = None,
    ) -> GroundedAnswer:
        abstain, reason = should_abstain(grounded_context)
        if abstain:
            return self._abstention_response(
                query=query,
                grounded_context=grounded_context,
                reason=reason,
                rewritten_query=rewritten_query,
            )

        answer_text, provider_name, model_used, in_tok, out_tok = generate_answer(
            provider=self.provider,
            query=query,
            grounded_context=grounded_context,
            model=self.model,
        )

        if answer_text.strip() == ABSTENTION_TEXT:
            return self._abstention_response(
                query=query,
                grounded_context=grounded_context,
                reason="model_self_abstained",
                rewritten_query=rewritten_query,
                provider=provider_name,
                model=model_used,
                usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok, total_calls=1),
            )

        citations = build_citations(answer_text, grounded_context.context_blocks)
        citation_coverage, validation_warnings = validate_answer(
            answer_text, grounded_context.context_blocks
        )

        hallucination = (
            validate_grounded_answer(
                provider=self.judge_provider,
                answer=answer_text,
                grounded_context=grounded_context,
                judge_model=self.judge_model,
            )
            if self.run_judge
            else HallucinationCheck()
        )

        usage = TokenUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            judge_input_tokens=hallucination.judge_input_tokens,
            judge_output_tokens=hallucination.judge_output_tokens,
            total_calls=1 + (1 if hallucination.judge_used else 0),
        )

        post_abstain, post_reason = should_abstain(grounded_context, hallucination=hallucination)
        if post_abstain and post_reason and post_reason.startswith("high_hallucination_risk"):
            return self._abstention_response(
                query=query,
                grounded_context=grounded_context,
                reason=post_reason,
                rewritten_query=rewritten_query,
                hallucination=hallucination,
                provider=provider_name,
                model=model_used,
                usage=usage,
            )

        confidence = compute_answer_confidence(grounded_context, hallucination, citation_coverage)
        warnings = list(grounded_context.grounding_warnings) + validation_warnings

        return GroundedAnswer(
            query=query,
            answer=answer_text,
            citations=citations,
            confidence=confidence,
            grounding_warnings=warnings,
            hallucination=hallucination,
            abstained=False,
            used_chunks=[c.chunk_id for c in citations],
            rewritten_query=rewritten_query,
            provider=provider_name,
            model=model_used,
            usage=usage,
        )

    def _abstention_response(
        self,
        query: str,
        grounded_context: GroundedContext,
        reason: str | None,
        rewritten_query: str | None = None,
        hallucination: HallucinationCheck | None = None,
        provider: str = "",
        model: str = "",
        usage: TokenUsage | None = None,
    ) -> GroundedAnswer:
        return GroundedAnswer(
            query=query,
            answer=ABSTENTION_TEXT,
            citations=[],
            confidence=AnswerConfidence(
                grounding_confidence=grounded_context.grounding_confidence
            ),
            grounding_warnings=list(grounded_context.grounding_warnings),
            hallucination=hallucination or HallucinationCheck(),
            abstained=True,
            abstention_reason=reason,
            used_chunks=[],
            rewritten_query=rewritten_query,
            provider=provider,
            model=model,
            usage=usage or TokenUsage(),
        )
