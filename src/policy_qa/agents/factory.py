"""Construction of Microsoft Agent Framework agents with deterministic options.

All agents share a fixed seed and a pinned model version. gpt-5-family
reasoning models fix temperature/top_p at the platform level (only the default
is accepted), so the deterministic levers here are: fixed seed (best-effort per
OpenAI), pinned model deployment, schema-constrained structured outputs, exact
retrieval, and fixed prompts.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence, TypeVar

from agent_framework import Agent, AgentResponse
from agent_framework.openai import (
    OpenAIChatCompletionClient,
    OpenAIChatCompletionOptions,
)
from pydantic import BaseModel, ValidationError

from ..config import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)

DETERMINISTIC_OPTIONS: OpenAIChatCompletionOptions[Any] = {"seed": 42}


def make_chat_client(settings: Settings) -> OpenAIChatCompletionClient:
    return OpenAIChatCompletionClient(
        model=settings.chat_deployment,
        api_key=settings.aoai_api_key,
        azure_endpoint=settings.aoai_endpoint,
        api_version=settings.aoai_api_version,
    )


def make_agent(
    client: OpenAIChatCompletionClient,
    *,
    name: str,
    instructions: str,
    response_format: type[BaseModel] | None = None,
    tools: Sequence[Callable[..., Any]] | None = None,
) -> Agent:
    options: OpenAIChatCompletionOptions[Any] = DETERMINISTIC_OPTIONS.copy()
    if response_format is not None:
        options["response_format"] = response_format
    return Agent(
        client,
        instructions,
        name=name,
        tools=list(tools) if tools else None,
        default_options=options,
    )


class StructuredOutputError(RuntimeError):
    """Raised when an agent response cannot be parsed into its Pydantic contract."""


def parse_structured(response: AgentResponse, model: type[ModelT]) -> ModelT:
    """Extract the typed value from an agent response, tolerating both the
    parsed `.value` path and a raw-JSON `.text` fallback."""
    value = getattr(response, "value", None)
    if isinstance(value, model):
        return value
    try:
        return model.model_validate_json(response.text)
    except ValidationError as exc:
        raise StructuredOutputError(
            f"Agent output did not match {model.__name__}: {exc}"
        ) from exc
