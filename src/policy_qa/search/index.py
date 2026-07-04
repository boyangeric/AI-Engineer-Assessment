"""Azure AI Search index definition: keyword fields + vectors + semantic config."""

from __future__ import annotations

import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)

from ..config import Settings
from ..logging_setup import log_event

logger = logging.getLogger(__name__)

VECTOR_PROFILE = "hnsw-profile"
SEMANTIC_CONFIG = "semantic-default"


def build_index(settings: Settings) -> SearchIndex:
    fields = [
        SimpleField(name="id", type="Edm.String", key=True),
        SearchableField(name="control_id", type="Edm.String", filterable=True),
        SearchableField(name="title", type="Edm.String"),
        SearchableField(name="description", type="Edm.String"),
        SearchableField(
            name="category", type="Edm.String", filterable=True, facetable=True
        ),
        SimpleField(name="source", type="Edm.String", filterable=True),
        SearchField(
            name="content_vector",
            type="Collection(Edm.Single)",
            searchable=True,
            # Retrievable so the client can compute query<->doc cosine similarity
            # as an absolute relevance gate (RRF scores are only rank fusion).
            hidden=False,
            vector_search_dimensions=settings.embedding_dimensions,
            vector_search_profile_name=VECTOR_PROFILE,
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[
            VectorSearchProfile(
                name=VECTOR_PROFILE, algorithm_configuration_name="hnsw-config"
            )
        ],
    )
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name=SEMANTIC_CONFIG,
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="description")],
                    keywords_fields=[SemanticField(field_name="category")],
                ),
            )
        ]
    )
    return SearchIndex(
        name=settings.search_index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


def create_or_update_index(settings: Settings) -> None:
    client = SearchIndexClient(
        endpoint=settings.search_endpoint,
        credential=AzureKeyCredential(settings.search_api_key),
    )
    index = build_index(settings)
    client.create_or_update_index(index)
    log_event(logger, "index created or updated", index=settings.search_index_name)
