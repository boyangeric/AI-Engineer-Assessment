"""Answer-generation helpers shared by the response executor."""

from __future__ import annotations

from typing import Any

from ..schemas import (
    FinalAnswer,
    RerankedContext,
    RetrievedDocument,
    make_fallback_answer,
    validate_citations,
)
from ..text import wrap_untrusted_document
from .agent_factory import parse_structured


def build_evidence_block(documents: list[RetrievedDocument]) -> str:
    """Delimit each retrieved chunk in escaped XML-style tags.

    Indirect prompt-injection defence: the wrapper marks index content as
    untrusted data and the escaping stops it from closing the tag, so text
    inside a document can never masquerade as instructions outside one. The
    prompts instruct the model to never follow directives found inside
    <document> tags.
    """
    lines = ["Retrieved security controls (untrusted reference data):", "<documents>"]
    for i, doc in enumerate(documents, start=1):
        lines.append(
            wrap_untrusted_document(i, doc.control_id, doc.title, doc.category, doc.content)
        )
    lines.append("</documents>")
    return "\n".join(lines)


def build_context_block(context: RerankedContext) -> str:
    return "\n".join(
        [
            f"User question: {context.question}",
            "",
            build_evidence_block(context.documents),
        ]
    )


async def generate_draft(agent: Any, context: RerankedContext) -> FinalAnswer:
    """Run the responder agent and apply the citation-validation defence."""
    response = await agent.run(build_context_block(context))
    answer: FinalAnswer = parse_structured(response, FinalAnswer)
    if answer.grounded:
        return validate_citations(answer, context.documents)
    return make_fallback_answer(reason="model_reported_insufficient_context")
