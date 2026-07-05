"""Prompt-block builders shared by the responder and both grading gates.

Every block that carries retrieved index content applies the XML delimiting
and escaping that defends against indirect prompt injection, so the defence
lives in exactly one place.
"""

from __future__ import annotations

from ..schemas import RerankedContext, RetrievedDocument
from ..utils.text import wrap_untrusted_document


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
    """Question plus delimited evidence: the responder's full user prompt."""
    return "\n".join(
        [
            f"User question: {context.question}",
            "",
            build_evidence_block(context.documents),
        ]
    )


def build_grading_block(question: str, documents: list[RetrievedDocument]) -> str:
    """Question plus delimited evidence: the relevance grader's full prompt."""
    return "\n".join([f"User question: {question}", "", build_evidence_block(documents)])
