"""Retrieval Agent: a framework Agent that queries Azure AI Search via a tool.

Grounding design: the LLM decides *which* tool calls to make for the plan's
steps, but the structured evidence passed downstream is assembled directly
from the search service's actual responses (captured by the tool), never from
the model's own text. If the model fails to call the tool, the executor falls
back to executing the plan steps deterministically so retrieval always
reflects real index content.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from agent_framework import Executor, WorkflowContext, handler

from ..config import Settings
from ..logging_setup import log_event
from ..schemas import QueryPlan, RetrievalResult, RetrievedDocument
from ..search.client import SearchService
from .factory import make_agent

logger = logging.getLogger(__name__)

RETRIEVAL_INSTRUCTIONS = """\
You are a retrieval agent for an enterprise security policy system.
You are given a retrieval plan as JSON. For EACH step in the plan, call the
search_security_policies tool exactly once with that step's search query.
After all tool calls are done, reply with the single word: DONE.
Do not summarise or alter the search results yourself.
"""


def relevant_documents(
    documents: list[RetrievedDocument], settings: Settings
) -> tuple[list[RetrievedDocument], bool]:
    """Rank collected docs and decide whether any clears the relevance gate."""
    ranked = sorted(documents, key=lambda d: (d.similarity, d.score), reverse=True)
    top = ranked[: settings.retrieval_top_k]
    has_relevant = any(
        d.similarity >= settings.relevance_threshold
        or (d.reranker_score is not None and d.reranker_score >= settings.reranker_threshold)
        for d in top
    )
    return top, has_relevant


class RetrievalExecutor(Executor):
    """Workflow node: QueryPlan in, RetrievalResult (real search hits) out."""

    def __init__(
        self,
        chat_client: Any,
        search_service: SearchService,
        settings: Settings,
        trace: dict[str, Any],
    ):
        super().__init__(id="retrieval")
        self._chat_client = chat_client
        self._search = search_service
        self._settings = settings
        self._trace = trace

    def _make_tool(self, collected: dict[str, RetrievedDocument]) -> Callable[[str], str]:
        def search_security_policies(query: str) -> str:
            """Search the enterprise security policy index (NIST SP 800-53 Rev 5)
            and return the matching controls as JSON."""
            documents = self._search.hybrid_search(query)
            for doc in documents:
                existing = collected.get(doc.id)
                if existing is None or doc.similarity > existing.similarity:
                    collected[doc.id] = doc
            return json.dumps(
                [
                    {"control_id": d.control_id, "title": d.title, "similarity": d.similarity}
                    for d in documents
                ]
            )

        return search_security_policies

    @handler
    async def retrieve(self, plan: QueryPlan, ctx: WorkflowContext[RetrievalResult]) -> None:
        started = time.perf_counter()
        collected: dict[str, RetrievedDocument] = {}
        agent = make_agent(
            self._chat_client,
            name="retrieval",
            instructions=RETRIEVAL_INSTRUCTIONS,
            tools=[self._make_tool(collected)],
        )
        try:
            await agent.run("Execute this retrieval plan:\n" + plan.model_dump_json(indent=2))
        except Exception:
            logger.exception("retrieval agent run failed; falling back to direct execution")

        if not collected:
            # Safety net: execute the plan deterministically so downstream
            # always receives real index content.
            log_event(logger, "retrieval agent made no tool calls; executing plan directly")
            tool = self._make_tool(collected)
            for step in plan.steps:
                tool(step.search_query)

        documents, has_relevant = relevant_documents(list(collected.values()), self._settings)
        result = RetrievalResult(
            plan=plan, documents=documents, has_relevant_results=has_relevant
        )
        latency_ms = round((time.perf_counter() - started) * 1000)
        self._trace["retrieval"] = result
        log_event(
            logger,
            "retrieval completed",
            agent="retrieval",
            input=[s.search_query for s in plan.steps],
            output={
                "documents": [
                    {"control_id": d.control_id, "similarity": d.similarity} for d in documents
                ],
                "has_relevant_results": has_relevant,
            },
            latency_ms=latency_ms,
        )
        await ctx.send_message(result)
