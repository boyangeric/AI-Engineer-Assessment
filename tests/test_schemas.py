"""Tests for the structured inter-agent contracts."""

import pytest
from pydantic import ValidationError

from policy_qa.schemas import (
    FALLBACK_ANSWER_TEXT,
    FaithfulnessGrade,
    FinalAnswer,
    QueryPlan,
    RetrievedDocument,
    SearchStep,
    make_fallback_answer,
    validate_citations,
)


def _doc(control_id: str) -> RetrievedDocument:
    return RetrievedDocument(
        id=control_id.lower().replace("(", "_").replace(")", ""),
        control_id=control_id,
        title="t",
        category="c",
        content="content",
        score=0.03,
    )


def test_query_plan_requires_between_one_and_three_steps():
    with pytest.raises(ValidationError):
        QueryPlan(original_query="q", interpretation="i", steps=[])
    plan = QueryPlan(
        original_query="q",
        interpretation="i",
        steps=[SearchStep(step_id=1, search_query="access control", rationale="r")],
    )
    assert plan.steps[0].search_query == "access control"


def test_validate_citations_strips_unretrieved_controls():
    answer = FinalAnswer(
        answer="a", citations=["AC-2", "ZZ-99"], confidence="high", grounded=True
    )
    validated = validate_citations(answer, [_doc("AC-2")])
    assert validated.citations == ["AC-2"]
    assert validated.grounded is True


def test_validate_citations_falls_back_when_nothing_valid():
    answer = FinalAnswer(
        answer="a", citations=["ZZ-99"], confidence="high", grounded=True
    )
    validated = validate_citations(answer, [_doc("AC-2")])
    assert validated.grounded is False
    assert validated.citations == []
    assert "could not find relevant information" in validated.answer.lower()


def test_validate_citations_recovers_retrieved_id_from_inline_answer():
    answer = FinalAnswer(
        answer="Use adaptive authentication as specified by IA-10.",
        citations=[],
        confidence="medium",
        grounded=True,
    )
    validated = validate_citations(answer, [_doc("IA-10")])
    assert validated.citations == ["IA-10"]
    assert validated.grounded is True


def test_validate_citations_normalizes_decorated_control_id():
    answer = FinalAnswer(
        answer="Apply the retrieved control.",
        citations=["AC-2 (1) — Automated System Account Management"],
        confidence="medium",
        grounded=True,
    )
    validated = validate_citations(answer, [_doc("AC-2(1)")])
    assert validated.citations == ["AC-2(1)"]


@pytest.mark.parametrize(
    "reason,expected_phrase",
    [
        ("no_relevant_results", "could not find relevant information"),
        ("moderation_blocked", "content moderation"),
        ("faithfulness_failed", "grounding quality check"),
        ("some_unknown_reason", "could not find relevant information"),
    ],
)
def test_fallback_answer_message_matches_reason(reason, expected_phrase):
    answer = make_fallback_answer(reason=reason)
    assert answer.grounded is False
    assert answer.citations == []
    assert answer.confidence == "low"
    assert expected_phrase in answer.answer.lower()


def test_unknown_fallback_reason_uses_default_text():
    assert make_fallback_answer(reason="pipeline_error").answer == FALLBACK_ANSWER_TEXT


def test_grader_scores_are_bounded_to_unit_interval():
    with pytest.raises(ValidationError):
        FaithfulnessGrade(faithfulness_score=1.5)
    assert FaithfulnessGrade(faithfulness_score=0.8).unsupported_claims == []
