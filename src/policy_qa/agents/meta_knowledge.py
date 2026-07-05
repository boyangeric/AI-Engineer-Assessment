"""Meta-knowledge node: deterministic answers about the assistant itself.

Reached when the Planner classifies a question as `meta_knowledge` (identity,
scope, capabilities). The response is deterministic — self-description needs no
evidence and must not invent any — so, like the fallback node, this executor
never makes an LLM call. It is kept separate from the Response Agent, whose sole
job is grounded generation from retrieved evidence.
"""

from __future__ import annotations

import logging
from typing import Any, Never

from agent_framework import Executor, WorkflowContext, handler

from ..utils.logging_setup import log_event
from ..schemas import FinalAnswer, QueryPlan, make_meta_knowledge_answer
from ..tracing import TraceState

logger = logging.getLogger(__name__)


class MetaKnowledgeExecutor(Executor):
    """Terminal node for meta questions about the assistant — no LLM call."""

    def __init__(self, trace: TraceState):
        super().__init__(id="meta_knowledge")
        self._trace = trace

    @handler
    async def respond(
        self, plan: QueryPlan, ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        answer = make_meta_knowledge_answer()
        self._trace.answer = answer
        log_event(
            logger,
            "meta question answered without LLM call",
            agent="meta_knowledge",
            input={"intent": plan.intent.value, "question": plan.original_query},
            output=answer.model_dump(),
            latency_ms=0,
        )
        await ctx.yield_output(answer)
