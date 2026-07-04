"""Planner Agent: decomposes the user question into structured search steps."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ..logging_setup import log_event
from ..schemas import QueryPlan
from .factory import parse_structured

logger = logging.getLogger(__name__)

PLANNER_INSTRUCTIONS = """\
You are a query planner for an enterprise security policy question-answering system.
The knowledge base is the NIST SP 800-53 Rev 5 security control catalog indexed in
Azure AI Search (fields: control id, title, description, control family).

Decompose the user's question into 1-3 focused search steps. Each step must contain
a short keyword-style search query targeting security controls, plus a one-sentence
rationale. Use multiple steps only when the question genuinely spans distinct topics.
Do not answer the question yourself.
"""


class PlannerExecutor(Executor):
    """Workflow node wrapping the Planner Agent; emits a typed QueryPlan."""

    def __init__(self, agent: Any, trace: dict[str, Any]):
        super().__init__(id="planner")
        self._agent = agent
        self._trace = trace

    @handler
    async def plan(self, query: str, ctx: WorkflowContext[QueryPlan]) -> None:
        started = time.perf_counter()
        response = await self._agent.run(query)
        plan = parse_structured(response, QueryPlan)
        plan = plan.model_copy(update={"original_query": query})
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["plan"] = plan
        log_event(
            logger,
            "planner completed",
            agent="planner",
            input=query,
            output=plan.model_dump(),
            latency_ms=latency_ms,
        )
        await ctx.send_message(plan)
