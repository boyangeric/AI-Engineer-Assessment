"""Tests for the safe-fallback behaviour (no hallucination paths)."""

import asyncio
import inspect
from dataclasses import replace

from policy_qa.agents.responder import ResponseExecutor
from policy_qa.agents.retrieval import relevant_documents
from policy_qa.config import Settings
from policy_qa.schemas import (
    FinalAnswer,
    QueryPlan,
    RetrievalResult,
    RetrievedDocument,
    SearchStep,
)


def _settings(**overrides) -> Settings:
    base = Settings(
        aoai_endpoint="https://example.openai.azure.com/",
        aoai_api_key="test",
        aoai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        search_endpoint="https://example.search.windows.net",
        search_api_key="test",
        search_index_name="idx",
        relevance_threshold=0.30,
    )
    return replace(base, **overrides) if overrides else base


def _doc(similarity: float) -> RetrievedDocument:
    return RetrievedDocument(
        id="ac-2",
        control_id="AC-2",
        title="Account Management",
        category="Access Control",
        content="c",
        score=0.03,
        similarity=similarity,
    )


def _plan() -> QueryPlan:
    return QueryPlan(
        original_query="q",
        interpretation="i",
        steps=[SearchStep(step_id=1, search_query="q", rationale="r")],
    )


def test_relevance_gate_rejects_low_similarity():
    docs, has_relevant = relevant_documents([_doc(0.12)], _settings())
    assert has_relevant is False
    assert len(docs) == 1  # documents still surfaced for transparency


def test_relevance_gate_accepts_high_similarity():
    _, has_relevant = relevant_documents([_doc(0.55)], _settings())
    assert has_relevant is True


class _ExplodingAgent:
    """The fallback path must never invoke the LLM."""

    async def run(self, *args, **kwargs):
        raise AssertionError("LLM was called on the fallback path")


class _CapturingContext:
    def __init__(self):
        self.outputs = []

    async def yield_output(self, value):
        self.outputs.append(value)


def test_responder_short_circuits_without_llm_call():
    executor = ResponseExecutor(_ExplodingAgent(), trace={})
    result = RetrievalResult(plan=_plan(), documents=[_doc(0.1)], has_relevant_results=False)
    ctx = _CapturingContext()
    respond = inspect.unwrap(ResponseExecutor.respond)  # undecorated handler
    asyncio.run(respond(executor, result, ctx))
    answer = ctx.outputs[0]
    assert isinstance(answer, FinalAnswer)
    assert answer.grounded is False
    assert answer.citations == []
