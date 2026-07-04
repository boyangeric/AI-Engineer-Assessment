"""Tests for the structured inter-agent contracts."""

import pytest
from pydantic import ValidationError

from policy_qa.schemas import (
    FinalAnswer,
    QueryPlan,
    RetrievedDocument,
    SearchStep,
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
        similarity=0.5,
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
