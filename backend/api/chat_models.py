from __future__ import annotations

from pydantic import BaseModel, Field

from backend.answering.models.answer import GroundedAnswer
from backend.conversation.validators import ConversationState


class AnswerRequest(BaseModel):
    query: str
    top_k: int = 5
    candidate_pool: int = 20
    token_budget: int = 2000
    include_components: bool = False
    run_judge: bool = True
    provider: str | None = None
    model: str | None = None
    use_cache: bool = True


class ChatRequest(AnswerRequest):
    session_id: str | None = None


class CacheHitInfo(BaseModel):
    hit: bool = False
    similarity: float | None = None
    primary_section_type: str | None = None
    cache_age_seconds: float | None = None


class ChatResponse(BaseModel):
    session_id: str
    answer: GroundedAnswer
    rewritten_query: str | None = None
    was_rewritten: bool = False
    cache: CacheHitInfo = Field(default_factory=CacheHitInfo)
    conversation_state: ConversationState
