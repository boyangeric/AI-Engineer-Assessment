"""Application configuration loaded from environment variables (12-factor style).

All settings are validated at startup so misconfiguration fails fast with a
clear message instead of surfacing as a confusing runtime error mid-query.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
Verbosity = Literal["low", "medium", "high"]


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _require(name: str, missing: list[str]) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        missing.append(name)
    return value


@dataclass(frozen=True)
class Settings:
    # Azure OpenAI
    aoai_endpoint: str
    aoai_api_key: str
    aoai_api_version: str
    chat_deployment: str
    embedding_deployment: str

    # Azure AI Search
    search_endpoint: str
    search_api_key: str
    search_index_name: str

    # Retrieval behaviour
    retrieval_top_k: int = 5
    reranker_threshold: float = 1.5
    use_semantic_ranker: bool = True

    # Grading thresholds (all scores on a 0-1 scale)
    context_relevance_score_threshold: float = 0.5
    faithfulness_score_threshold: float = 0.7

    # Determinism levers shared by every agent
    llm_seed: int = 42
    llm_verbosity: Verbosity = "low"

    # Workflow safety bound: hard cap on graph supersteps per query
    workflow_max_iterations: int = 12

    # Evaluation harness
    judge_evidence_chars: int = 400

    # Misc
    log_level: str = "INFO"
    log_file: Path = field(default=PROJECT_ROOT / "logs" / "policy-qa.jsonl")
    log_to_console: bool = False
    embedding_dimensions: int = field(default=1536, init=True)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or PROJECT_ROOT / ".env")

        missing: list[str] = []
        settings = cls(
            aoai_endpoint=_require("AZURE_OPENAI_ENDPOINT", missing),
            aoai_api_key=_require("AZURE_OPENAI_API_KEY", missing),
            aoai_api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            chat_deployment=_require("AZURE_OPENAI_CHAT_DEPLOYMENT", missing),
            embedding_deployment=_require("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", missing),
            search_endpoint=_require("AZURE_SEARCH_ENDPOINT", missing),
            search_api_key=_require("AZURE_SEARCH_API_KEY", missing),
            search_index_name=os.environ.get("AZURE_SEARCH_INDEX_NAME", "security-policies"),
            retrieval_top_k=int(os.environ.get("RETRIEVAL_TOP_K", "5")),
            reranker_threshold=float(os.environ.get("RERANKER_THRESHOLD", "1.5")),
            use_semantic_ranker=os.environ.get("USE_SEMANTIC_RANKER", "true").lower()
            in ("1", "true", "yes"),
            context_relevance_score_threshold=float(
                os.environ.get("CONTEXT_RELEVANCE_SCORE_THRESHOLD", "0.5")
            ),
            faithfulness_score_threshold=float(
                os.environ.get("FAITHFULNESS_SCORE_THRESHOLD", "0.7")
            ),
            llm_seed=int(os.environ.get("LLM_SEED", "42")),
            llm_verbosity=_verbosity_from_env(),
            workflow_max_iterations=int(os.environ.get("WORKFLOW_MAX_ITERATIONS", "12")),
            judge_evidence_chars=int(os.environ.get("JUDGE_EVIDENCE_CHARS", "400")),
            log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
            log_file=Path(
                os.environ.get(
                    "LOG_FILE", str(PROJECT_ROOT / "logs" / "policy-qa.jsonl")
                )
            ),
            log_to_console=os.environ.get("LOG_TO_CONSOLE", "false").lower()
            in ("1", "true", "yes"),
        )
        if missing:
            raise ConfigError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in the values."
            )
        if not 3 <= settings.retrieval_top_k <= 20:
            raise ConfigError("RETRIEVAL_TOP_K must be between 3 and 20.")
        for name in (
            "context_relevance_score_threshold",
            "faithfulness_score_threshold",
        ):
            if not 0.0 <= getattr(settings, name) <= 1.0:
                raise ConfigError(f"{name.upper()} must be between 0 and 1.")
        return settings


def _verbosity_from_env() -> Verbosity:
    value = os.environ.get("LLM_VERBOSITY", "low").strip().lower()
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    raise ConfigError("LLM_VERBOSITY must be one of: low, medium, high.")
