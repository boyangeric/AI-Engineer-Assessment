"""Moderation contracts: the grader output and its typed edge message."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModerationVerdict(BaseModel):
    """LLM output of the moderation grader."""

    allowed: bool = Field(description="True when the question is safe to process")
    category: str = Field(
        default="none", description="Violation category when blocked, e.g. 'prompt_injection'"
    )
    reason: str = Field(default="", description="Short explanation of the verdict")


class ContentModerationResponse(BaseModel):
    """Moderation node output: whether the question may enter the pipeline."""

    question: str
    allowed: bool = Field(description="True when the question is safe to process")
    category: str = Field(
        default="none", description="Violation category when blocked, e.g. 'prompt_injection'"
    )
    reason: str = Field(default="", description="Short explanation of the verdict")
