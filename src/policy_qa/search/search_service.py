"""Hybrid (keyword + vector) search against Azure AI Search.

Azure AI Search owns candidate retrieval and ordering. When semantic ranking is
enabled, Azure also returns `@search.reranker_score`, which the workflow uses
as a stronger relevance signal without introducing a second client-side ranking
system.
"""

from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from ..config import Settings
from ..utils.logging_setup import log_event
from ..utils.retry import transient_retry
from ..schemas import RetrievedDocument
from .embeddings import EmbeddingService
from .index_schema import SEMANTIC_CONFIG

logger = logging.getLogger(__name__)

_SELECT_FIELDS = ["id", "control_id", "title", "category", "description"]


class SearchService:
    def __init__(self, settings: Settings, embeddings: EmbeddingService | None = None):
        self._settings = settings
        self._embeddings = embeddings or EmbeddingService(settings)
        self._client = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index_name,
            credential=AzureKeyCredential(settings.search_api_key),
        )

    @transient_retry(attempts=4, max_wait=30)
    def _execute_search_request(self, query: str, vector: list[float], top_k: int, semantic: bool):
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
        """Run hybrid search and return typed documents in Azure's ranked order."""
        top_k = top_k or self._settings.retrieval_top_k
        query_vector = self._embeddings.embed_one(query)

        semantic = self._settings.use_semantic_ranker
        try:
            results = self._execute_search_request(query, query_vector, top_k, semantic)
        except HttpResponseError as exc:
            if semantic:
                # Semantic ranker unavailable (e.g. Free tier) -> plain hybrid.
                log_event(
                    logger,
                    "semantic ranker unavailable, retrying plain hybrid",
                    error=str(exc.message),
                )
                results = self._execute_search_request(query, query_vector, top_k, semantic=False)
            else:
                raise

        documents: list[RetrievedDocument] = []
        for hit in results:
            documents.append(
                RetrievedDocument(
                    id=hit["id"],
                    control_id=hit["control_id"],
                    title=hit["title"],
                    category=hit["category"],
                    content=hit["description"],
                    score=hit["@search.score"],
                    reranker_score=hit.get("@search.reranker_score"),
                )
            )
        log_event(
            logger,
            "hybrid search executed",
            query=query,
            semantic_ranker_requested=semantic,
            semantic_ranker_exercised=any(
                document.reranker_score is not None for document in documents
            ),
            top_k=top_k,
            results=[
                {
                    "control_id": d.control_id,
                    "score": d.score,
                    "reranker_score": d.reranker_score,
                }
                for d in documents
            ],
        )
        return documents

    def get_document_count(self) -> int:
        return self._client.get_document_count()
