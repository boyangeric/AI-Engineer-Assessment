"""Ingestion contract: the document shape stored in the search index."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PolicyRecord(BaseModel):
    """One security control as stored in the Azure AI Search index."""

    id: str = Field(description="Search-safe document key, e.g. 'ac-2_1'")
    control_id: str = Field(description="Human control identifier, e.g. 'AC-2(1)'")
    title: str
    description: str
    category: str = Field(description="Control family, e.g. 'Access Control'")
    source: str = "NIST SP 800-53 Rev 5"
