"""Hybrid (keyword + vector) search against Azure AI Search.

Relevance gating: the hybrid RRF score only reflects rank fusion, not absolute
relevance, so the client also computes the cosine similarity between the query
embedding and each document's stored embedding. That similarity is an absolute
signal used to decide whether retrieval found anything trustworthy (the
fallback gate). When the semantic ranker is enabled (Basic tier and above) the
reranker score is used as an additional signal.
"""

from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from ..config import Settings
from ..logging_setup import log_event
from ..schemas import RetrievedDocument
from .embeddings import EmbeddingService, cosine_similarity
from .index import SEMANTIC_CONFIG

logger = logging.getLogger(__name__)

_SELECT_FIELDS = ["id", "control_id", "title", "category", "description", "content_vector"]


def _is_transient(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    return status in (429, 500, 502, 503, 504)


class SearchService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService | None = None):
        self._settings = settings
        self._embeddings = embeddings or EmbeddingService(settings)
        self._client = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index_name,
            credential=AzureKeyCredential(settings.search_api_key),
        )

    @retry(
        retry=retry_if_exception(_is_transient),
        wait=wait_exponential(multiplier=2, max=30),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _run_search(self, query: str, vector: list[float], top_k: int, semantic: bool):
        kwargs: dict = {
            "search_text": query,
            "vector_queries": [
                VectorizedQuery(
                    vector=vector, k_nearest_neighbors=50, fields="content_vector"
                )
            ],
            "select": _SELECT_FIELDS,
            "top": top_k,
        }
        if semantic:
            kwargs["query_type"] = "semantic"
            kwargs["semantic_configuration_name"] = SEMANTIC_CONFIG
        return list(self._client.search(**kwargs))

    def hybrid_search(self, query: str, top_k: int | None = None) -> list[RetrievedDocument]:
        """Run hybrid search and return typed, similarity-scored documents."""
        top_k = top_k or self._settings.retrieval_top_k
        query_vector = self._embeddings.embed_one(query)

        semantic = self._settings.use_semantic_ranker
        try:
            results = self._run_search(query, query_vector, top_k, semantic)
        except HttpResponseError as exc:
            if semantic:
                # Semantic ranker unavailable (e.g. Free tier) -> plain hybrid.
                log_event(
                    logger,
                    "semantic ranker unavailable, retrying plain hybrid",
                    error=str(exc.message),
                )
                results = self._run_search(query, query_vector, top_k, semantic=False)
            else:
                raise

        documents: list[RetrievedDocument] = []
        for hit in results:
            doc_vector = hit.get("content_vector") or []
            documents.append(
                RetrievedDocument(
                    id=hit["id"],
                    control_id=hit["control_id"],
                    title=hit["title"],
                    category=hit["category"],
                    content=hit["description"],
                    score=hit["@search.score"],
                    similarity=round(cosine_similarity(query_vector, doc_vector), 4),
                    reranker_score=hit.get("@search.reranker_score"),
                )
            )
        log_event(
            logger,
            "hybrid search executed",
            query=query,
            top_k=top_k,
            results=[
                {"control_id": d.control_id, "similarity": d.similarity, "score": d.score}
                for d in documents
            ],
        )
        return documents

    def document_count(self) -> int:
        return self._client.get_document_count()
