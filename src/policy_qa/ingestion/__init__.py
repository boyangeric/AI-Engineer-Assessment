"""Catalog ingestion: download, OSCAL transform, embed, and index."""

from .pipeline import run_ingestion

__all__ = ["run_ingestion"]
