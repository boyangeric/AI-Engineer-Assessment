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

from ...config import Settings

ModelT = TypeVar("ModelT", bound=BaseModel)

def deterministic_options(settings: Settings) -> OpenAIChatCompletionOptions[Any]:
    """Reproducibility options shared by every agent, sourced from Settings."""
    return {
        "seed": settings.llm_seed,
        "verbosity": settings.llm_verbosity,
    }


def build_chat_client(settings: Settings) -> OpenAIChatCompletionClient:
    """Build the shared Azure OpenAI chat client bound to the pinned deployment.

    Args:
        settings: Configuration holding the Azure OpenAI endpoint, API key,
            API version, and the pinned chat deployment name.

    Returns:
        An `OpenAIChatCompletionClient` ready to back one or more agents.
    """
    return OpenAIChatCompletionClient(
        model=settings.chat_deployment,
        api_key=settings.aoai_api_key,
        azure_endpoint=settings.aoai_endpoint,
        api_version=settings.aoai_api_version,
    )


def build_deterministic_agent(
    client: OpenAIChatCompletionClient,
    settings: Settings,
    *,
    name: str,
    instructions: str,
    response_format: type[BaseModel] | None = None,
    tools: Sequence[Callable[..., Any]] | None = None,
) -> Agent:
    """Build a framework Agent pre-configured with the deterministic options.

    Every agent in the pipeline is created through this factory so they all
    share the same reproducibility levers (fixed seed, pinned deployment via
    `client`, fixed prompt) rather than each call site choosing its own.

    Args:
        client: Chat client bound to the pinned Azure OpenAI deployment.
        settings: Configuration providing the shared determinism levers.
        name: Agent name used in framework traces and logs.
        instructions: System prompt (a versioned prompt from `policy_qa.prompts`).
        response_format: Optional Pydantic model enforcing schema-constrained structured output.
        tools: Optional callables the agent may invoke (e.g. the search tool).

    Returns:
        A configured `agent_framework.Agent` ready to `run()`.
    """
    options: OpenAIChatCompletionOptions[Any] = deterministic_options(settings)
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
