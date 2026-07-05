"""Retrieval Agent executor: execute every plan step against Azure AI Search.

The Planner already supplies structured search steps, so another LLM call adds
latency without adding reasoning. Searches run concurrently, and final selection
reserves coverage across steps before filling remaining slots by similarity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agent_framework import Executor, WorkflowContext, handler

from ..config import Settings
from ..logging_setup import log_event
from ..schemas import QueryPlan, RetrievalResult, RetrievedDocument
from ..search.search_service import SearchService

logger = logging.getLogger(__name__)


def select_diverse_documents(
    result_sets: list[list[RetrievedDocument]], settings: Settings
) -> tuple[list[RetrievedDocument], bool]:
    """Select top evidence while preserving at least one result per plan step."""
    selected: list[RetrievedDocument] = []
    selected_ids: set[str] = set()

    for documents in result_sets:
        ranked = sorted(
            documents, key=lambda document: (document.similarity, document.score), reverse=True
        )
        for document in ranked:
            if document.id not in selected_ids:
                selected.append(document)
                selected_ids.add(document.id)
                break

    remaining = sorted(
        (document for documents in result_sets for document in documents),
        key=lambda document: (document.similarity, document.score),
        reverse=True,
    )
    for document in remaining:
        if len(selected) >= settings.retrieval_top_k:
            break
        if document.id not in selected_ids:
            selected.append(document)
            selected_ids.add(document.id)

    top = selected[: settings.retrieval_top_k]
    has_relevant = any(
        document.similarity >= settings.relevance_threshold
        or (
            document.reranker_score is not None
            and document.reranker_score >= settings.reranker_threshold
        )
        for document in top
    )
    return top, has_relevant


class RetrievalExecutor(Executor):
    """Workflow node: QueryPlan in, structured Azure search evidence out."""

    def __init__(
        self,
        search_service: SearchService,
        settings: Settings,
        trace: dict[str, Any],
    ):
        super().__init__(id="retrieval")
        self._search = search_service
        self._settings = settings
        self._trace = trace

    @handler
    async def retrieve(self, plan: QueryPlan, ctx: WorkflowContext[RetrievalResult]) -> None:
        started = time.perf_counter()
        result_sets = await asyncio.gather(
            *(
                asyncio.to_thread(self._search.hybrid_search, step.search_query)
                for step in plan.steps
            )
        )
        documents, has_relevant = select_diverse_documents(
            list(result_sets), self._settings
        )
        result = RetrievalResult(
            plan=plan,
            documents=documents,
            has_relevant_results=has_relevant,
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["retrieval"] = result
        log_event(
            logger,
            "retrieval completed",
            agent="retrieval",
            input=[step.search_query for step in plan.steps],
            output={
                "documents": [
                    {"control_id": document.control_id, "similarity": document.similarity}
                    for document in documents
                ],
                "has_relevant_results": has_relevant,
            },
            latency_ms=latency_ms,
        )
        await ctx.send_message(result)
