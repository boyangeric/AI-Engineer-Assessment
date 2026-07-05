"""Retrieval contracts: search hits and the ranked evidence carried on edges."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .planning import QueryPlan


class RetrievedDocument(BaseModel):
    """One search hit returned by Azure AI Search, with relevance signals."""

    id: str
    control_id: str
    title: str
    category: str
    content: str
    score: float = Field(description="Hybrid RRF score from Azure AI Search")
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
