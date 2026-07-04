"""Response Agent: generates the final answer strictly from retrieved evidence.

Hallucination defences, in order:
1. If retrieval found nothing above the relevance threshold, a canned fallback
   is returned WITHOUT any model call.
2. The model is instructed to answer only from the numbered context and to
   cite control IDs.
3. After generation, citations are validated against the actually-retrieved
   controls; an answer with no valid citation is replaced by the fallback.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Never

from agent_framework import Executor, WorkflowContext, handler

from ..logging_setup import log_event
from ..schemas import (
    FinalAnswer,
    RetrievalResult,
    make_fallback_answer,
    validate_citations,
)
from .factory import parse_structured

logger = logging.getLogger(__name__)

RESPONDER_INSTRUCTIONS = """\
You are a security policy assistant answering questions for compliance officers.
Answer ONLY using the numbered security controls provided in the message.
Rules:
- Every claim must come from the provided controls. Do not use outside knowledge.
- Cite the control IDs you used (e.g. "AC-2(1)") in the citations list, and
  reference them inline in the answer text.
- If the provided controls do not contain enough information to answer, say so
  explicitly, set grounded=false and leave citations empty.
- Be concise and structured; use short paragraphs or bullet points.
"""


def build_context_block(result: RetrievalResult) -> str:
    lines = [f"User question: {result.plan.original_query}", "", "Retrieved security controls:"]
    for i, doc in enumerate(result.documents, start=1):
        lines.append(
            f"\n[{i}] {doc.control_id} — {doc.title} (family: {doc.category})\n{doc.content}"
        )
    return "\n".join(lines)


class ResponseExecutor(Executor):
    """Workflow node: RetrievalResult in, FinalAnswer yielded as workflow output."""

    def __init__(self, agent: Any, trace: dict[str, Any]):
        super().__init__(id="responder")
        self._agent = agent
        self._trace = trace

    @handler
    async def respond(
        self, result: RetrievalResult, ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        started = time.perf_counter()

        if not result.has_relevant_results or not result.documents:
            answer = make_fallback_answer(reason="no_relevant_results")
            self._trace["answer"] = answer
            log_event(
                logger,
                "responder short-circuited to safe fallback (no LLM call)",
                agent="responder",
                input={"documents": len(result.documents)},
                output=answer.model_dump(),
                latency_ms=0,
            )
            await ctx.yield_output(answer)
            return

        response = await self._agent.run(build_context_block(result))
        answer: FinalAnswer = parse_structured(response, FinalAnswer)
        if answer.grounded:
            answer = validate_citations(answer, result.documents)
        else:
            answer = make_fallback_answer(reason="model_reported_insufficient_context")

        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["answer"] = answer
        log_event(
            logger,
            "responder completed",
            agent="responder",
            input={"documents": [d.control_id for d in result.documents]},
            output=answer.model_dump(),
            latency_ms=latency_ms,
        )
        await ctx.yield_output(answer)
