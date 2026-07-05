"""Pydantic contracts for every inter-agent message.

These models are the single source of truth for the structured data that
flows Planner -> Retrieval -> Response, for the search index documents, and
for the evaluation rubric. Agents never exchange free-form text.

Split by pipeline domain; everything is re-exported here so consumers import
from `policy_qa.schemas` regardless of which submodule defines a contract.
"""

from .answers import (
    FALLBACK_ANSWER_TEXT,
    FALLBACK_MESSAGES,
    META_KNOWLEDGE_ANSWER_TEXT,
    DraftAnswer,
    FinalAnswer,
    make_fallback_answer,
    make_meta_knowledge_answer,
    validate_citations,
)
from .grading import (
    ContextRelevanceGrade,
    DocumentRelevance,
    FaithfulnessGrade,
    FaithfulnessResult,
    JudgeScore,
)
from .moderation import ContentModerationResponse, ModerationVerdict
from .planning import QueryIntent, QueryPlan, SearchStep
from .records import PolicyRecord
from .retrieval import RerankedContext, RetrievalResult, RetrievedDocument

__all__ = [
    "FALLBACK_ANSWER_TEXT",
    "FALLBACK_MESSAGES",
    "META_KNOWLEDGE_ANSWER_TEXT",
    "ContentModerationResponse",
    "ContextRelevanceGrade",
    "DocumentRelevance",
    "DraftAnswer",
    "FaithfulnessGrade",
    "FaithfulnessResult",
    "FinalAnswer",
    "JudgeScore",
    "ModerationVerdict",
    "PolicyRecord",
    "QueryIntent",
    "QueryPlan",
    "RerankedContext",
    "RetrievalResult",
    "RetrievedDocument",
    "SearchStep",
    "make_fallback_answer",
    "make_meta_knowledge_answer",
    "validate_citations",
]
