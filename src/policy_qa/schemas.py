"""Pydantic contracts for every inter-agent message.

These models are the single source of truth for the structured data that
flows Planner -> Retrieval -> Response, for the search index documents, and
for the evaluation rubric. Agents never exchange free-form text.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field


class PolicyRecord(BaseModel):
    """One security control as stored in the Azure AI Search index."""

    id: str = Field(description="Search-safe document key, e.g. 'ac-2_1'")
    control_id: str = Field(description="Human control identifier, e.g. 'AC-2(1)'")
    title: str
    description: str
    category: str = Field(description="Control family, e.g. 'Access Control'")
    source: str = "NIST SP 800-53 Rev 5"


class SearchStep(BaseModel):
    """One focused retrieval step produced by the Planner Agent."""

    step_id: int
    search_query: str = Field(description="Focused query for the policy index")
    rationale: str = Field(description="Why this step is needed to answer the question")


class QueryPlan(BaseModel):
    """Planner Agent output: the user question decomposed into search steps."""

    original_query: str
    interpretation: str = Field(description="What the user is really asking")
    steps: list[SearchStep] = Field(min_length=1, max_length=3)


class RetrievedDocument(BaseModel):
    """One search hit returned by Azure AI Search, with relevance signals."""

    id: str
    control_id: str
    title: str
    category: str
    content: str
    score: float = Field(description="Hybrid RRF score from Azure AI Search")
    similarity: float = Field(
        default=0.0, description="Cosine similarity between query and document embeddings"
    )
    reranker_score: float | None = Field(
        default=None, description="Semantic reranker score when the ranker is enabled"
    )


class RetrievalResult(BaseModel):
    """Retrieval Agent output: deduplicated, ranked evidence for the responder."""

    plan: QueryPlan
    documents: list[RetrievedDocument]
    has_relevant_results: bool = Field(
        description="True when at least one document clears the relevance threshold"
    )


class FinalAnswer(BaseModel):
    """Response Agent output: the grounded answer shown to the user."""

    answer: str
    citations: list[str] = Field(
        default_factory=list,
        description="Control IDs the answer is based on; must be a subset of retrieved docs",
    )
    confidence: Literal["high", "medium", "low"]
    grounded: bool = Field(
        description="False when the safe fallback was used instead of a model answer"
    )


# --- LLM grader outputs (schema-constrained structured outputs) ---------------
# Each grader agent produces one of these small models; the executor wraps it
# into the richer edge message below, adding the question/draft/retry context
# the model itself must not invent.


class ModerationVerdict(BaseModel):
    """LLM output of the moderation grader."""

    allowed: bool = Field(description="True when the question is safe to process")
    category: str = Field(
        default="none", description="Violation category when blocked, e.g. 'prompt_injection'"
    )
    reason: str = Field(default="", description="Short explanation of the verdict")


class DocumentRelevance(BaseModel):
    """One document's graded relevance within a ContextRelevanceGrade."""

    control_id: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class ContextRelevanceGrade(BaseModel):
    """LLM output of the context relevance grader (all docs in one call)."""

    scores: list[DocumentRelevance]
    reasoning: str = ""


class FaithfulnessGrade(BaseModel):
    """LLM output of the hallucination grader."""

    faithfulness_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = every claim supported by the evidence"
    )
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str = ""


# --- Edge messages (typed contracts carried on graph edges) --------------------


class ContentModerationResponse(BaseModel):
    """Moderation node output: whether the question may enter the pipeline."""

    question: str
    allowed: bool = Field(description="True when the question is safe to process")
    category: str = Field(
        default="none", description="Violation category when blocked, e.g. 'prompt_injection'"
    )
    reason: str = Field(default="", description="Short explanation of the verdict")


class RerankedContext(BaseModel):
    """Context relevance grader output: LLM-reranked evidence for the responder."""

    question: str
    plan: QueryPlan
    documents: list[RetrievedDocument] = Field(
        description="reranked_docs: docs clearing the context relevance threshold, best first"
    )
    relevance_scores: dict[str, float] = Field(
        default_factory=dict, description="control_id -> graded relevance score (0-1)"
    )


class DraftAnswer(BaseModel):
    """Responder output: a candidate answer awaiting faithfulness grading."""

    answer: FinalAnswer
    context: RerankedContext


class FaithfulnessResult(BaseModel):
    """Hallucination grader output: how well the draft is supported by evidence."""

    draft: DraftAnswer
    faithfulness_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = every claim supported by the evidence"
    )
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str = ""


class JudgeScore(BaseModel):
    """LLM-judge rubric used by the evaluation harness."""

    retrieval_relevance: int = Field(ge=1, le=5)
    groundedness: int = Field(ge=1, le=5)
    justification: str


FALLBACK_ANSWER_TEXT = (
    "I could not find relevant information in the indexed security policy corpus "
    "(NIST SP 800-53 Rev 5) to answer this question. Please rephrase the question "
    "or consult your security team directly."
)

# Reason-specific safe responses; anything unlisted uses FALLBACK_ANSWER_TEXT.
FALLBACK_MESSAGES: dict[str, str] = {
    "moderation_blocked": (
        "This request was declined by the content moderation check. This assistant "
        "only answers questions about enterprise security policy (NIST SP 800-53 "
        "Rev 5). Please rephrase your question."
    ),
    "faithfulness_failed": (
        "An answer was generated but did not pass the system's grounding quality "
        "check, so it was withheld rather than risk giving you "
        "unsupported information. Please rephrase the question or consult your "
        "security team directly."
    ),
}


def make_fallback_answer(reason: str = "no_relevant_results") -> FinalAnswer:
    """Deterministic safe response used whenever grounding cannot be guaranteed."""
    return FinalAnswer(
        answer=FALLBACK_MESSAGES.get(reason, FALLBACK_ANSWER_TEXT),
        citations=[],
        confidence="low",
        grounded=False,
    )


def validate_citations(answer: FinalAnswer, documents: list[RetrievedDocument]) -> FinalAnswer:
    """Keep citations that refer to an actually-retrieved control.

    Models occasionally decorate a citation (for example, ``"AC-2 — Account
    Management"``) or put the control ID inline while omitting it from the
    structured citations field. Canonicalize both forms before deciding that
    an otherwise-grounded answer has no evidence.
    """
    control_pattern = re.compile(
        r"\b([A-Z]{2,3})\s*-\s*(\d+)(?:\s*\(\s*(\d+)\s*\))?",
        re.IGNORECASE,
    )

    def canonical_ids(text: str) -> list[str]:
        return [
            f"{family.upper()}-{number}" + (f"({enhancement})" if enhancement else "")
            for family, number, enhancement in control_pattern.findall(text)
        ]

    retrieved_ids = {d.control_id.upper(): d.control_id for d in documents}
    candidates: list[str] = []
    for citation in answer.citations:
        candidates.extend(canonical_ids(citation))
    candidates.extend(canonical_ids(answer.answer))

    valid: list[str] = []
    for candidate in candidates:
        actual = retrieved_ids.get(candidate)
        if actual and actual not in valid:
            valid.append(actual)
    if not valid:
        return make_fallback_answer(reason="no_valid_citations")
    return answer.model_copy(update={"citations": valid, "grounded": True})
