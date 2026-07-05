"""Single post-generation faithfulness gate."""

from __future__ import annotations

import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ..config import Settings
from ..utils.logging_setup import log_event
from ..schemas import DraftAnswer, FaithfulnessGrade, FaithfulnessResult, FinalAnswer
from ..tracing import TraceState
from .agent_factory import parse_structured
from .prompt_blocks import build_faithfulness_block

logger = logging.getLogger(__name__)


class FaithfulnessGraderExecutor(Executor):
    """Workflow node: DraftAnswer in, FaithfulnessResult out (routing on edges)."""

    def __init__(self, agent: Any, settings: Settings, trace: TraceState):
        super().__init__(id="faithfulness_grader")
        self._agent = agent
        self._threshold = settings.faithfulness_score_threshold
        self._trace = trace

    @handler
    async def grade(
        self,
        draft: DraftAnswer,
        ctx: WorkflowContext[FaithfulnessResult, FinalAnswer],
    ) -> None:
        started = time.perf_counter()
        prompt = build_faithfulness_block(draft.context, draft.answer.answer)
        response = await self._agent.run(prompt)
        grade = parse_structured(response, FaithfulnessGrade)
        result = FaithfulnessResult(draft=draft, **grade.model_dump())
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace.faithfulness.append(grade.model_dump())
        log_event(
            logger,
            "faithfulness grading completed",
            agent="faithfulness_grader",
            input={"answer_chars": len(draft.answer.answer)},
            output={
                **grade.model_dump(),
                "passed": grade.faithfulness_score >= self._threshold,
            },
            latency_ms=latency_ms,
        )
        if grade.faithfulness_score >= self._threshold:
            self._trace.answer = draft.answer
            await ctx.yield_output(draft.answer)
            return
        await ctx.send_message(result)
