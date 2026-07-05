"""Fallback node: terminal safe answers for every failure path — never an LLM call.

Reached when moderation blocks the question, no document survives context
relevance, or the generated answer fails faithfulness. Each incoming message
maps to a reason-specific deterministic response.
"""

from __future__ import annotations

import logging
from typing import Any, Never

from agent_framework import Executor, WorkflowContext, handler

from ..logging_setup import log_event
from ..schemas import (
    ContentModerationResponse,
    FaithfulnessResult,
    FinalAnswer,
    RerankedContext,
    make_fallback_answer,
)

logger = logging.getLogger(__name__)


class FallbackExecutor(Executor):
    """Terminal node for every safe-failure path — never makes an LLM call."""

    def __init__(self, trace: dict[str, Any]):
        super().__init__(id="fallback")
        self._trace = trace

    async def _yield_fallback(
        self, reason: str, detail: dict[str, Any], ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        answer = make_fallback_answer(reason=reason)
        self._trace["answer"] = answer
        self._trace["fallback_reason"] = reason
        log_event(
            logger,
            "fallback answered without LLM call",
            agent="fallback",
            input={"reason": reason, **detail},
            output=answer.model_dump(),
            latency_ms=0,
        )
        await ctx.yield_output(answer)

    @handler
    async def on_moderation_block(
        self, result: ContentModerationResponse, ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        await self._yield_fallback(
            "moderation_blocked", {"category": result.category}, ctx
        )

    @handler
    async def on_no_reranked_docs(
        self, result: RerankedContext, ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        await self._yield_fallback(
            "no_relevant_results", {"reranked_docs": len(result.documents)}, ctx
        )

    @handler
    async def on_faithfulness_failure(
        self, result: FaithfulnessResult, ctx: WorkflowContext[Never, FinalAnswer]
    ) -> None:
        await self._yield_fallback(
            "faithfulness_failed",
            {"faithfulness_score": result.faithfulness_score},
            ctx,
        )
