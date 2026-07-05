"""Answer contracts and the deterministic safe-response factories."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from ..utils.text import normalize_control_id
from .retrieval import RerankedContext, RetrievedDocument


class FinalAnswer(BaseModel):
    """Response Agent output: the grounded answer shown to the user."""

    answer: str
    citations: list[str] = Field(
        default_factory=list,
        description="Control IDs the answer is based on; must be a subset of retrieved docs",
    )
    confidence: Literal["high", "medium", "low"]
    grounded: bool = Field(
        description="False when the safe fallback was used instead of a model answer"
    )


class DraftAnswer(BaseModel):
    """Responder output: a candidate answer awaiting faithfulness grading."""

    answer: FinalAnswer
    context: RerankedContext


FALLBACK_ANSWER_TEXT = (
    "I could not find relevant information in the indexed security policy corpus "
    "(NIST SP 800-53 Rev 5) to answer this question. Please rephrase the question "
    "or consult your security team directly."
)

# Deterministic answer for meta questions about the assistant itself. Served
# without an LLM call: self-description needs no evidence and must not invent
# any. Kept free of specific corpus statistics (control counts, family counts)
# so it cannot drift out of sync with the actual index.
META_KNOWLEDGE_ANSWER_TEXT = (
    "I am an enterprise security policy assistant. My knowledge base is the "
    "NIST SP 800-53 Rev 5 security control catalog, indexed in Azure AI Search "
    "and spanning control families such as Access Control, Audit and "
    "Accountability, and System and Communications Protection. Ask me about "
    "security policy requirements — for example access control, logging and "
    "monitoring, or data protection — and I will answer strictly from the "
    "retrieved controls, with citations. I cannot answer questions outside "
    "this catalog."
)

# Reason-specific safe responses; anything unlisted uses FALLBACK_ANSWER_TEXT.
FALLBACK_MESSAGES: dict[str, str] = {
    "moderation_blocked": (
        "This request was declined by the content moderation check. This assistant "
        "only answers questions about enterprise security policy (NIST SP 800-53 "
        "Rev 5). Please rephrase your question."
    ),
    "out_of_domain": (
        "This question falls outside the indexed security policy corpus "
        "(NIST SP 800-53 Rev 5), so no answer was attempted. Please ask about "
        "enterprise security policy — for example access control, logging and "
        "monitoring, or incident response."
    ),
    "faithfulness_failed": (
        "An answer was generated but did not pass the system's grounding quality "
        "check, so it was withheld rather than risk giving you "
        "unsupported information. Please rephrase the question or consult your "
        "security team directly."
    ),
}


def make_meta_knowledge_answer() -> FinalAnswer:
    """Deterministic self-description for meta questions — never an LLM call."""
    return FinalAnswer(
        answer=META_KNOWLEDGE_ANSWER_TEXT,
        citations=[],
        confidence="high",
        grounded=True,
    )


def make_fallback_answer(reason: str = "no_relevant_results") -> FinalAnswer:
    """Deterministic safe response used whenever grounding cannot be guaranteed."""
    return FinalAnswer(
        answer=FALLBACK_MESSAGES.get(reason, FALLBACK_ANSWER_TEXT),
        citations=[],
        confidence="low",
        grounded=False,
    )


def validate_citations(answer: FinalAnswer, documents: list[RetrievedDocument]) -> FinalAnswer:
    """Keep citations that refer to an actually-retrieved control.

    Models occasionally decorate a citation (for example, ``"AC-2 — Account
    Management"``) or put the control ID inline while omitting it from the
    structured citations field. Canonicalize both forms before deciding that
    an otherwise-grounded answer has no evidence.
    """
    control_pattern = re.compile(
        r"\b([A-Z]{2,3})\s*-\s*(\d+)(?:\s*\(\s*(\d+)\s*\))?",
        re.IGNORECASE,
    )

    def canonical_ids(text: str) -> list[str]:
        return [
            f"{family.upper()}-{number}" + (f"({enhancement})" if enhancement else "")
            for family, number, enhancement in control_pattern.findall(text)
        ]

    retrieved_ids = {normalize_control_id(d.control_id): d.control_id for d in documents}
    candidates: list[str] = []
    for citation in answer.citations:
        candidates.extend(canonical_ids(citation))
    candidates.extend(canonical_ids(answer.answer))

    valid: list[str] = []
    for candidate in candidates:
        actual = retrieved_ids.get(candidate)
        if actual and actual not in valid:
            valid.append(actual)
    if not valid:
        return make_fallback_answer(reason="no_valid_citations")
    return answer.model_copy(update={"citations": valid, "grounded": True})
