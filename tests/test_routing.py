"""Tests for workflow routing and graph type compatibility."""

import pytest

from agent_framework.openai import OpenAIChatCompletionClient
from policy_qa.agents import build_chat_client
from policy_qa.config import Settings
from policy_qa.graph import (
    build_workflow,
    has_reranked_documents,
    is_meta_knowledge,
    is_policy_question,
    moderation_passed,
)
from policy_qa.schemas import (
    ContentModerationResponse,
    QueryIntent,
    QueryPlan,
    RerankedContext,
    RetrievedDocument,
    SearchStep,
)
from policy_qa.search import SearchService
from policy_qa.tracing import TraceState


def _settings() -> Settings:
    return Settings(
        aoai_endpoint="https://example.openai.azure.com/",
        aoai_api_key="test",
        aoai_api_version="2024-10-21",
        chat_deployment="gpt-5-mini",
        embedding_deployment="text-embedding-3-small",
        search_endpoint="https://example.search.windows.net",
        search_api_key="test",
        search_index_name="idx",
    )


def _context(documents: list[RetrievedDocument]) -> RerankedContext:
    plan = QueryPlan(
        original_query="q",
        interpretation="i",
        steps=[SearchStep(step_id=1, search_query="q", rationale="r")],
    )
    return RerankedContext(question="q", plan=plan, documents=documents)


def _doc() -> RetrievedDocument:
    return RetrievedDocument(
        id="ac-2",
        control_id="AC-2",
        title="Account Management",
        category="Access Control",
        content="c",
        score=0.03,
    )


def test_chat_client_uses_azure_openai():
    assert isinstance(build_chat_client(_settings()), OpenAIChatCompletionClient)


def test_semantic_ranker_is_enabled_by_default():
    assert _settings().use_semantic_ranker is True


def test_moderation_gate():
    assert moderation_passed(ContentModerationResponse(question="q", allowed=True))
    assert not moderation_passed(
        ContentModerationResponse(question="q", allowed=False, category="harmful")
    )
    assert not moderation_passed("not a message")


def _plan(intent: QueryIntent) -> QueryPlan:
    steps = (
        [SearchStep(step_id=1, search_query="q", rationale="r")]
        if intent is QueryIntent.policy_question
        else []
    )
    return QueryPlan(original_query="q", interpretation="i", intent=intent, steps=steps)


def test_intent_router_sends_policy_questions_to_retrieval():
    assert is_policy_question(_plan(QueryIntent.policy_question))
    assert not is_policy_question(_plan(QueryIntent.meta_knowledge))
    assert not is_policy_question(_plan(QueryIntent.out_of_domain))
    assert not is_policy_question("not a message")


def test_intent_router_sends_meta_questions_to_responder():
    assert is_meta_knowledge(_plan(QueryIntent.meta_knowledge))
    assert not is_meta_knowledge(_plan(QueryIntent.policy_question))
    assert not is_meta_knowledge(_plan(QueryIntent.out_of_domain))
    assert not is_meta_knowledge("not a message")


def test_policy_question_plan_requires_search_steps():
    with pytest.raises(ValueError):
        QueryPlan(
            original_query="q",
            interpretation="i",
            intent=QueryIntent.policy_question,
            steps=[],
        )


def test_grounding_gate_requires_a_reranked_document():
    assert has_reranked_documents(_context([_doc()]))
    assert not has_reranked_documents(_context([]))


def test_complete_workflow_has_compatible_edge_types():
    settings = _settings()
    workflow = build_workflow(
        build_chat_client(settings),
        SearchService(settings),
        settings,
        TraceState(),
    )
    assert workflow is not None
