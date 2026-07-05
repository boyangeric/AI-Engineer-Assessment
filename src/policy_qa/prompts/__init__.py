"""Versioned prompt store.

Prompts are governed artifacts, not string literals buried in code: each one
lives in its own file named `{agent}_v{N}.md`, so changes are reviewable and
diffable in pull requests, and a release pins exactly the prompt versions it
shipped with.

The active version per agent is declared in ACTIVE_VERSIONS and can be
overridden per agent through an environment variable
(e.g. `PROMPT_VERSION_PLANNER=2`) — enabling A/B tests or an instant rollback
without a code change.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from importlib.resources import files

from ..utils.logging_setup import log_event

logger = logging.getLogger(__name__)

# Prompts used by the runtime query pipeline (graph.py).
RUNTIME_VERSIONS: dict[str, int] = {
    "moderation": 1,
    "planner": 1,
    "context_relevance_grader": 1,
    "responder": 2,
    "faithfulness_grader": 2,
}

# Prompts used only by the evaluation harness (evaluator.py), never at runtime.
EVAL_VERSIONS: dict[str, int] = {
    "judge": 1,
}

ACTIVE_VERSIONS: dict[str, int] = {**RUNTIME_VERSIONS, **EVAL_VERSIONS}


class PromptNotFoundError(RuntimeError):
    pass


def load_prompt(agent: str, version: int | None = None) -> str:
    """Return the prompt text for `agent`.

    Resolution order: explicit `version` argument, then the
    `PROMPT_VERSION_<AGENT>` environment variable, then ACTIVE_VERSIONS.
    """
    if agent not in ACTIVE_VERSIONS:
        raise PromptNotFoundError(f"Unknown agent '{agent}'. Known: {sorted(ACTIVE_VERSIONS)}")
    if version is None:
        version = int(os.environ.get(f"PROMPT_VERSION_{agent.upper()}", ACTIVE_VERSIONS[agent]))
    return _read_prompt(agent, version)


@lru_cache(maxsize=None)
def _read_prompt(agent: str, version: int) -> str:
    resource = files(__package__).joinpath(f"{agent}_v{version}.md")
    if not resource.is_file():
        raise PromptNotFoundError(f"No prompt file for agent '{agent}' version {version}")
    text = resource.read_text(encoding="utf-8")
    log_event(logger, "prompt loaded", agent=agent, prompt_version=version, chars=len(text))
    return text
