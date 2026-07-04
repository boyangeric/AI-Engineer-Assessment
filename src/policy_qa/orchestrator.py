"""Workflow orchestration: Planner -> Retrieval -> Response.

The three agents are wired as typed executors in a Microsoft Agent Framework
workflow graph. Messages between nodes are Pydantic models (QueryPlan,
RetrievalResult, FinalAnswer) — structured data, never free text.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agent_framework import WorkflowBuilder

from .agents.factory import make_agent, make_chat_client
from .agents.planner import PLANNER_INSTRUCTIONS, PlannerExecutor
from .agents.responder import RESPONDER_INSTRUCTIONS, ResponseExecutor
from .agents.retrieval import RetrievalExecutor
from .config import Settings
from .logging_setup import log_event, new_correlation_id
from .schemas import FinalAnswer, QueryPlan, RetrievalResult, make_fallback_answer
from .search.client import SearchService

logger = logging.getLogger(__name__)


@dataclass
class QueryTrace:
    """Full record of one query's journey through the pipeline."""

    question: str
    correlation_id: str
    answer: FinalAnswer
    plan: QueryPlan | None = None
    retrieval: RetrievalResult | None = None
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "correlation_id": self.correlation_id,
            "plan": self.plan.model_dump() if self.plan else None,
            "retrieval": self.retrieval.model_dump() if self.retrieval else None,
            "answer": self.answer.model_dump(),
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class Orchestrator:
    settings: Settings
    _search: SearchService = field(init=False)
    _chat_client: Any = field(init=False)

    def __post_init__(self) -> None:
        self._search = SearchService(self.settings)
        self._chat_client = make_chat_client(self.settings)

    async def run_query(self, question: str) -> QueryTrace:
        correlation_id = new_correlation_id()
        started = time.perf_counter()
        log_event(logger, "query received", question=question)

        trace_data: dict[str, Any] = {}
        planner = PlannerExecutor(
            make_agent(
                self._chat_client,
                name="planner",
                instructions=PLANNER_INSTRUCTIONS,
                response_format=QueryPlan,
            ),
            trace_data,
        )
        retriever = RetrievalExecutor(self._chat_client, self._search, self.settings, trace_data)
        responder = ResponseExecutor(
            make_agent(
                self._chat_client,
                name="responder",
                instructions=RESPONDER_INSTRUCTIONS,
                response_format=FinalAnswer,
            ),
            trace_data,
        )
        workflow = (
            WorkflowBuilder(start_executor=planner)
            .add_edge(planner, retriever)
            .add_edge(retriever, responder)
            .build()
        )

        error: str | None = None
        try:
            result = await workflow.run(question)
            outputs = result.get_outputs()
            if not outputs or not isinstance(outputs[0], FinalAnswer):
                raise RuntimeError("workflow produced no FinalAnswer output")
            answer = outputs[0]
        except Exception as exc:
            logger.exception("query pipeline failed")
            error = f"{type(exc).__name__}: {exc}"
            answer = make_fallback_answer(reason="pipeline_error")

        duration_ms = round((time.perf_counter() - started) * 1000)
        trace = QueryTrace(
            question=question,
            correlation_id=correlation_id,
            answer=answer,
            plan=trace_data.get("plan"),
            retrieval=trace_data.get("retrieval"),
            duration_ms=duration_ms,
            error=error,
        )
        log_event(
            logger,
            "query completed",
            grounded=answer.grounded,
            citations=answer.citations,
            duration_ms=duration_ms,
            error=error,
        )
        return trace
