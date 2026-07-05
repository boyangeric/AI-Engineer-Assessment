"""Response Agent: generates the candidate answer strictly from reranked evidence.

Hallucination defences, in order:
1. If no document survived the context relevance gate, a canned fallback is
   returned WITHOUT any model call (defence in depth behind the graph edge).
2. The model is instructed to answer only from the numbered context and to
   cite control IDs.
3. After generation, citations are validated against the actually-retrieved
   controls; an answer with no valid citation degrades to the fallback.
4. The emitted DraftAnswer must pass the faithfulness gate before it reaches
   the user.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ..logging_setup import log_event
from ..schemas import DraftAnswer, FinalAnswer, RerankedContext, make_fallback_answer
from .answer_draft_generation import generate_draft

logger = logging.getLogger(__name__)


class ResponseExecutor(Executor):
    """Workflow node: RerankedContext in, DraftAnswer out (to the quality gates)."""

    def __init__(self, agent: Any, trace: dict[str, Any]):
        super().__init__(id="responder")
        self._agent = agent
        self._trace = trace

    @handler
    async def respond(
        self, context: RerankedContext, ctx: WorkflowContext[DraftAnswer, FinalAnswer]
    ) -> None:
        started = time.perf_counter()

        if not context.documents:
            # Defence in depth: the graph edge should already have routed an
            # empty RerankedContext to the fallback.
            answer = make_fallback_answer(reason="no_relevant_results")
            self._trace["answer"] = answer
            self._trace["fallback_reason"] = "no_relevant_results"
            log_event(
                logger,
                "responder short-circuited to safe fallback (no LLM call)",
                agent="responder",
                input={"documents": 0},
                output=answer.model_dump(),
                latency_ms=0,
            )
            await ctx.yield_output(answer)
            return

        answer = await generate_draft(self._agent, context)
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["answer"] = answer
        log_event(
            logger,
            "responder completed",
            agent="responder",
            input={"documents": [d.control_id for d in context.documents]},
            output=answer.model_dump(),
            latency_ms=latency_ms,
        )
        if not answer.grounded:
            # Citation validation degraded the draft; grading canned text is
            # pointless, so terminate safely here.
            self._trace["fallback_reason"] = "no_valid_citations"
            await ctx.yield_output(answer)
            return
        await ctx.send_message(DraftAnswer(answer=answer, context=context))
