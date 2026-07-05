"""Planner Agent contracts: intent classification and search-step decomposition."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SearchStep(BaseModel):
    """One focused retrieval step produced by the Planner Agent."""

    step_id: int
    search_query: str = Field(description="Focused query for the policy index")
    rationale: str = Field(description="Why this step is needed to answer the question")


class QueryIntent(str, Enum):
    """Planner-classified intent of the user question; drives graph routing."""

    policy_question = "policy_question"
    meta_knowledge = "meta_knowledge"
    out_of_domain = "out_of_domain"


class QueryPlan(BaseModel):
    """Planner Agent output: classified intent plus decomposed search steps.

    `steps` is populated only for `policy_question`; the other intents bypass
    retrieval entirely, so their plans carry no search steps.
    """

    original_query: str
    interpretation: str = Field(description="What the user is really asking")
    intent: QueryIntent = Field(
        default=QueryIntent.policy_question,
        description="policy_question -> retrieval; meta_knowledge -> responder; "
        "out_of_domain -> fallback",
    )
    steps: list[SearchStep] = Field(
        default_factory=list,
        max_length=3,
        description="1-3 focused search steps; empty unless intent is policy_question",
    )

    @model_validator(mode="after")
    def _steps_match_intent(self) -> "QueryPlan":
        if self.intent is QueryIntent.policy_question and not self.steps:
            raise ValueError("policy_question plans require at least one search step")
        return self
