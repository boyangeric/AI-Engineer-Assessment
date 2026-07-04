"""Pydantic contracts for every inter-agent message.

These models are the single source of truth for the structured data that
flows Planner -> Retrieval -> Response, for the search index documents, and
for the evaluation rubric. Agents never exchange free-form text.
"""

from __future__ import annotations

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


def make_fallback_answer(reason: str = "no_relevant_results") -> FinalAnswer:
    """Deterministic safe response used whenever grounding cannot be guaranteed."""
    return FinalAnswer(
        answer=FALLBACK_ANSWER_TEXT,
        citations=[],
        confidence="low",
        grounded=False,
    )


def validate_citations(answer: FinalAnswer, documents: list[RetrievedDocument]) -> FinalAnswer:
    """Strip any citation that does not refer to an actually-retrieved control.

    If nothing valid remains the answer cannot be trusted as grounded, so the
    safe fallback is returned instead.
    """
    retrieved_ids = {d.control_id.upper() for d in documents}
    valid = [c for c in answer.citations if c.upper() in retrieved_ids]
    if not valid:
        return make_fallback_answer(reason="no_valid_citations")
    return answer.model_copy(update={"citations": valid, "grounded": True})
