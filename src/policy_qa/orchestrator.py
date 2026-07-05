"""Runtime facade around the workflow graph.

Owns the Azure clients, runs one query through the graph defined in
`graph.py`, guards every failure path into a typed fallback answer, and
returns the full QueryTrace for logging, the CLI and the evaluator.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .agents import build_chat_client
from .config import Settings
from .graph import build_workflow
from .utils.logging_setup import log_event, new_correlation_id
from .schemas import FinalAnswer, make_fallback_answer
from .search.search_service import SearchService
from .tracing import QueryTrace, TraceState

logger = logging.getLogger(__name__)


@dataclass
class Orchestrator:
    settings: Settings
    _search: SearchService = field(init=False)
    _chat_client: Any = field(init=False)

    def __post_init__(self) -> None:
        self._search = SearchService(self.settings)
        self._chat_client = build_chat_client(self.settings)

    async def run_query(self, question: str) -> QueryTrace:
        correlation_id = new_correlation_id()
        started = time.perf_counter()
        log_event(logger, "query received", question=question)

        trace_data = TraceState()
        workflow = build_workflow(self._chat_client, self._search, self.settings, trace_data)

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
        log_event(
            logger,
            "query completed",
            grounded=answer.grounded,
            citations=answer.citations,
            duration_ms=duration_ms,
            error=error,
        )
        return QueryTrace.from_run(
            question, correlation_id, answer, trace_data, duration_ms, error
        )
