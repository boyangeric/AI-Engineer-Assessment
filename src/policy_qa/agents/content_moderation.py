"""Content moderation gate: blocks unsafe input before any retrieval or generation.

First node in the graph. An LLM grader (structured output ModerationVerdict)
classifies the raw question; the executor wraps the verdict in a typed
ContentModerationResponse and the pass/block decision is a switch-case edge in
`graph.py`, so blocked questions route straight to the safe fallback without a
single downstream model or search call. Azure OpenAI's built-in content filter
remains a second, platform-level layer underneath this gate.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler
from agent_framework.exceptions import (
    AgentContentFilterException,
    ChatClientContentFilterException,
)

from ..logging_setup import log_event
from ..schemas import ContentModerationResponse, ModerationVerdict
from .agent_factory import parse_structured

logger = logging.getLogger(__name__)


class ModerationExecutor(Executor):
    """Workflow node wrapping the moderation grader; emits ContentModerationResponse."""

    def __init__(self, agent: Any, trace: dict[str, Any]):
        super().__init__(id="moderation")
        self._agent = agent
        self._trace = trace

    @handler
    async def moderate(self, question: str, ctx: WorkflowContext[ContentModerationResponse]) -> None:
        started = time.perf_counter()
        try:
            response = await self._agent.run(question)
            verdict = parse_structured(response, ModerationVerdict)
        except (AgentContentFilterException, ChatClientContentFilterException):
            # The platform content filter rejected the input before our grader
            # could even see it — that IS a block verdict, not a pipeline error.
            verdict = ModerationVerdict(
                allowed=False,
                category="platform_content_filter",
                reason="Blocked by the Azure OpenAI content filter.",
            )
        result = ContentModerationResponse(question=question, **verdict.model_dump())
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["moderation"] = result
        log_event(
            logger,
            "moderation completed",
            agent="moderation",
            input=question,
            output=result.model_dump(),
            latency_ms=latency_ms,
        )
        await ctx.send_message(result)
