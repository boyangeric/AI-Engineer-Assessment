"""Per-query trace records: typed stage state plus the final QueryTrace."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .schemas import (
    ContentModerationResponse,
    FinalAnswer,
    QueryPlan,
    RerankedContext,
    RetrievalResult,
)


@dataclass
class TraceState:
    """Mutable per-run state each executor writes its stage output into.

    Shared by every node in one workflow run and assembled into the immutable
    `QueryTrace` afterwards. Typed attributes (rather than a dict of string
    keys) so a misnamed stage write is an AttributeError, not a silently
    missing trace entry.
    """

    moderation: ContentModerationResponse | None = None
    plan: QueryPlan | None = None
    retrieval: RetrievalResult | None = None
    reranked: RerankedContext | None = None
    faithfulness: list[dict[str, Any]] = field(default_factory=list)
    answer: FinalAnswer | None = None
    fallback_reason: str | None = None


@dataclass
class QueryTrace:
    """Full record of one query's journey through the pipeline."""

    question: str
    correlation_id: str
    answer: FinalAnswer
    moderation: ContentModerationResponse | None = None
    plan: QueryPlan | None = None
    retrieval: RetrievalResult | None = None
    reranked: RerankedContext | None = None
    faithfulness: list[dict[str, Any]] = field(default_factory=list)
    fallback_reason: str | None = None
    duration_ms: int = 0
    error: str | None = None

    @classmethod
    def from_run(
        cls,
        question: str,
        correlation_id: str,
        answer: FinalAnswer,
        state: TraceState,
        duration_ms: int,
        error: str | None,
    ) -> "QueryTrace":
        """Assemble the trace from the stage outputs collected during a run."""
        return cls(
            question=question,
            correlation_id=correlation_id,
            answer=answer,
            moderation=state.moderation,
            plan=state.plan,
            retrieval=state.retrieval,
            reranked=state.reranked,
            faithfulness=state.faithfulness,
            fallback_reason=state.fallback_reason,
            duration_ms=duration_ms,
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "correlation_id": self.correlation_id,
            "moderation": self.moderation.model_dump() if self.moderation else None,
            "plan": self.plan.model_dump() if self.plan else None,
            "retrieval": self.retrieval.model_dump() if self.retrieval else None,
            "reranked": self.reranked.model_dump() if self.reranked else None,
            "faithfulness": self.faithfulness,
            "answer": self.answer.model_dump(),
            "fallback_reason": self.fallback_reason,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
