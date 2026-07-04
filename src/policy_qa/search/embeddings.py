"""Client-side embeddings via Azure OpenAI (text-embedding-3-small, 1536 dims).

Embeddings are computed client-side at both ingestion and query time so the
system behaves identically on every Azure AI Search tier (no dependency on
service-side vectorizers).
"""

from __future__ import annotations

import logging
import math

from openai import AzureOpenAI
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from ..config import Settings
from ..logging_setup import log_event

logger = logging.getLogger(__name__)

_MAX_CHARS = 24000


def _is_transient(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return status in (429, 500, 502, 503, 504)


class EmbeddingService:
    def __init__(self, settings: Settings):
        self._deployment = settings.embedding_deployment
        self._client = AzureOpenAI(
            azure_endpoint=settings.aoai_endpoint,
            api_key=settings.aoai_api_key,
            api_version=settings.aoai_api_version,
        )

    @retry(
        retry=retry_if_exception(_is_transient),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(
            model=self._deployment,
            input=[t[:_MAX_CHARS] for t in texts],
        )
        return [item.embedding for item in response.data]

    def embed(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors.extend(self._embed_batch(batch))
            log_event(logger, "embedded batch", start=i, size=len(batch))
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self._embed_batch([text])[0]

# Manual reranking signal, can be replaced by semantic reranker with a higher tier
def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
