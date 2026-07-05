"""Grader contracts: LLM grader outputs and their typed edge messages.

Each grader agent produces one of the small schema-constrained models; the
executor wraps it into the richer edge message, adding the question/draft/retry
context the model itself must not invent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .answers import DraftAnswer


class DocumentRelevance(BaseModel):
    """One document's graded relevance within a ContextRelevanceGrade."""

    control_id: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class ContextRelevanceGrade(BaseModel):
    """LLM output of the context relevance grader (all docs in one call)."""

    scores: list[DocumentRelevance]
    reasoning: str = ""


class FaithfulnessGrade(BaseModel):
    """LLM output of the faithfulness grader."""

    faithfulness_score: float = Field(
        ge=0.0, le=1.0, description="1.0 = every claim supported by the evidence"
    )
    unsupported_claims: list[str] = Field(default_factory=list)
    reasoning: str = ""


class FaithfulnessResult(BaseModel):
    """Faithfulness grader output: how well the draft is supported by evidence."""

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
