"""Context relevance node: LLM-graded reranking of the retrieved evidence.

One batched grader call scores every retrieved control against the question in
a single structured output (never N per-document calls); documents below
`context_relevance_score_threshold` are dropped and the survivors are sorted
best-first into `RerankedContext.documents` (the reranked_docs). The
empty/non-empty decision is a switch-case edge in `graph.py`.

Robustness, mirroring the retrieval executor's pattern:
- If retrieval already found nothing above the retrieval gate, the
  node emits an empty RerankedContext WITHOUT an LLM call (short-circuit).
- If the grader call itself fails, the node fails open to the retrieval-ranked
  documents; the downstream faithfulness gate remains the safety net.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ..config import Settings
from ..utils.logging_setup import log_event
from ..schemas import (
    ContextRelevanceGrade,
    RerankedContext,
    RetrievalResult,
    RetrievedDocument,
)
from ..utils.text import normalize_control_id
from ..tracing import TraceState
from .agent_factory import parse_structured
from .prompt_blocks import build_grading_block

logger = logging.getLogger(__name__)


def rerank_documents(
    documents: list[RetrievedDocument],
    grade: ContextRelevanceGrade,
    threshold: float,
) -> tuple[list[RetrievedDocument], dict[str, float]]:
    """Filter docs below the graded relevance threshold and sort best-first."""
    scores = {normalize_control_id(s.control_id): s.relevance_score for s in grade.scores}

    def score_of(document: RetrievedDocument) -> float:
        return scores.get(normalize_control_id(document.control_id), 0.0)

    kept = [d for d in documents if score_of(d) >= threshold]
    kept.sort(key=score_of, reverse=True)
    return kept, {d.control_id: score_of(d) for d in documents}


class ContextRelevanceExecutor(Executor):
    """Workflow node: RetrievalResult in, RerankedContext (reranked_docs) out."""

    def __init__(self, agent: Any, settings: Settings, trace: TraceState):
        super().__init__(id="relevance_grader")
        self._agent = agent
        self._settings = settings
        self._trace = trace

    @handler
    async def grade(
        self, retrieval: RetrievalResult, ctx: WorkflowContext[RerankedContext]
    ) -> None:
        started = time.perf_counter()
        question = retrieval.plan.original_query

        if not retrieval.documents or not retrieval.has_relevant_results:
            # The retrieval gate already ruled this out; no LLM call.
            result = RerankedContext(
                question=question, plan=retrieval.plan, documents=[], relevance_scores={}
            )
            self._trace.reranked = result
            log_event(
                logger,
                "context relevance short-circuited (nothing cleared retrieval gate)",
                agent="relevance_grader",
                input={"documents": len(retrieval.documents)},
                output={"reranked_docs": 0},
                latency_ms=0,
            )
            await ctx.send_message(result)
            return

        try:
            response = await self._agent.run(
                build_grading_block(question, retrieval.documents)
            )
            grade = parse_structured(response, ContextRelevanceGrade)
            documents, scores = rerank_documents(
                retrieval.documents, grade, self._settings.context_relevance_score_threshold
            )
        except Exception:
            # Fail open to retrieval-ranked evidence; the downstream
            # faithfulness gate still guards the final answer.
            logger.exception("context relevance grading failed; keeping retrieval order")
            documents, scores = retrieval.documents, {}

        result = RerankedContext(
            question=question, plan=retrieval.plan, documents=documents, relevance_scores=scores
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace.reranked = result
        log_event(
            logger,
            "context relevance grading completed",
            agent="relevance_grader",
            input={"documents": [d.control_id for d in retrieval.documents]},
            output={
                "reranked_docs": [d.control_id for d in documents],
                "relevance_scores": scores,
            },
            latency_ms=latency_ms,
        )
        await ctx.send_message(result)
