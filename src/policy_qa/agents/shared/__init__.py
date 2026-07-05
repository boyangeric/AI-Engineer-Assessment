"""Shared agent-construction and prompt-block helpers."""

from .agent_factory import (
    StructuredOutputError,
    build_chat_client,
    build_deterministic_agent,
    deterministic_options,
    parse_structured,
)
from .prompt_blocks import (
    build_context_block,
    build_evidence_block,
    build_faithfulness_block,
    build_grading_block,
    build_question_block,
)

__all__ = [
    "StructuredOutputError",
    "build_chat_client",
    "build_context_block",
    "build_deterministic_agent",
    "build_evidence_block",
    "build_faithfulness_block",
    "build_grading_block",
    "build_question_block",
    "deterministic_options",
    "parse_structured",
]
