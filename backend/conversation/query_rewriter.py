from __future__ import annotations

import regex as re

from backend.conversation.validators import ConversationState
from backend.llm.provider_interface import BaseLLMProvider
from backend.llm.validators import LLMMessage, LLMRequest


REWRITE_SYSTEM_PROMPT = (
    "You rewrite vague follow-up questions to be standalone. Use the conversation history "
    "and active entities to fill in implicit subjects. Return ONLY the rewritten question, "
    "without any extra prose, quotation marks, or commentary. If the new question is "
    "already standalone, return it unchanged."
)


FOLLOWUP_MARKERS: list[str] = [
    r"\bwhat about\b",
    r"\bhow about\b",
    r"\band (?:the |their |its |for )",
    r"\balso\b",
    r"\bfor that\b",
    r"\bthose\b",
    r"\bthat one\b",
    r"\bthe same\b",
    r"^\s*(?:and|or|but)\b",
    # Possessive / object pronouns — almost always reference an entity from a prior turn.
    # "what are her achievements" was running on raw text before this and retrieving the
    # wrong person; the rewriter must fire to substitute the named entity from history.
    r"\b(?:her|hers|his|him|their|theirs|them)\b",
    # Subject pronouns at the start of the question.
    r"^\s*(?:she|he|they|it)\b",
]


def is_followup_query(query: str, state: ConversationState) -> bool:
    """A query is a followup when there's prior context AND it contains an explicit
    followup marker ("what about", "and", "also", ...).

    We deliberately do NOT treat short queries as followups: "who is dr sunita barve" is
    fully standalone at 5 words, and sending it through the LLM rewriter produced garbage
    like "who is" that destroyed retrieval. Standalone short queries with proper nouns
    should pass through unchanged."""
    if not state.turns or not query:
        return False
    lower = query.lower()
    return any(re.search(pattern, lower) for pattern in FOLLOWUP_MARKERS)


def _rewrite_looks_sane(original: str, rewritten: str) -> bool:
    """Reject rewrites that lost too much of the original — usually a sign the LLM
    truncated or otherwise mangled the rewrite."""
    if not rewritten:
        return False
    orig_words = [w for w in re.split(r"\s+", original.strip()) if w]
    new_words = [w for w in re.split(r"\s+", rewritten.strip()) if w]
    if not orig_words:
        return True
    if len(new_words) < max(2, len(orig_words) * 0.6):
        return False
    return True


def _build_rewrite_prompt(query: str, state: ConversationState) -> str:
    recent_turns = "\n".join(
        f"{turn.role}: {turn.content[:200]}" for turn in state.turns[-4:]
    )
    entities = (
        ", ".join(f"{k}={v}" for k, v in state.active_entities.items()) or "(none)"
    )
    intent = state.last_intent or "(none)"
    return (
        f"Conversation so far:\n{recent_turns}\n\n"
        f"Active entities: {entities}\n"
        f"Last intent: {intent}\n\n"
        f"New question: {query}\n\n"
        f"Rewritten standalone question:"
    )


def rewrite_query(
    provider: BaseLLMProvider,
    query: str,
    state: ConversationState,
    model: str = "",
    max_tokens: int = 80,
) -> str:
    """Rewrite the query when it looks like a follow-up; otherwise return as-is.

    A failed LLM call returns the original query so the conversation continues with the
    raw text rather than aborting.
    """
    if not is_followup_query(query, state):
        return query

    request = LLMRequest(
        system_prompt=REWRITE_SYSTEM_PROMPT,
        messages=[LLMMessage(role="user", content=_build_rewrite_prompt(query, state))],
        model=model or provider.default_model,
        temperature=0.0,
        max_tokens=max_tokens,
    )
    try:
        response = provider.generate(request)
    except Exception:
        return query
    rewritten = (response.text or "").strip().strip('"').strip("'")
    if not rewritten or not _rewrite_looks_sane(query, rewritten):
        return query
    return rewritten
