"""Planner Agent: interpret and decompose a moderated user question."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ...utils.logging_setup import log_event
from ...schemas import ContentModerationResponse, QueryPlan
from ...tracing import TraceState
from ..shared.agent_factory import parse_structured

logger = logging.getLogger(__name__)


class PlannerExecutor(Executor):
    """Workflow node wrapping the Planner Agent; emits a typed QueryPlan."""

    def __init__(self, agent: Any, trace: TraceState):
        super().__init__(id="planner")
        self._agent = agent
        self._trace = trace

    async def _plan(self, query: str, ctx: WorkflowContext[QueryPlan]) -> None:
        started = time.perf_counter()
        response = await self._agent.run(query)
        plan = parse_structured(response, QueryPlan)
        plan = plan.model_copy(update={"original_query": query})
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace.plan = plan
        log_event(
            logger,
            "planner completed",
            agent="planner",
            input=query,
            output=plan.model_dump(),
            latency_ms=latency_ms,
        )
        await ctx.send_message(plan)

    @handler
    async def plan(
        self, moderated: ContentModerationResponse, ctx: WorkflowContext[QueryPlan]
    ) -> None:
        await self._plan(moderated.question, ctx)
