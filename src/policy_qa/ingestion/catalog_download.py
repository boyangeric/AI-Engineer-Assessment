"""Download and cache the NIST SP 800-53 Rev 5 catalog (OSCAL JSON)."""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT
from ..logging_setup import log_event

logger = logging.getLogger(__name__)

CATALOG_URL = (
    "https://raw.githubusercontent.com/usnistgov/oscal-content/main/"
    "nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json"
)
CACHE_PATH = PROJECT_ROOT / "data" / "raw" / "NIST_SP-800-53_rev5_catalog.json"


def download_catalog(force: bool = False) -> dict[str, Any]:
    """Return the OSCAL catalog, downloading it once and caching to data/raw/."""
    if CACHE_PATH.exists() and not force:
        log_event(logger, "catalog cache hit", path=str(CACHE_PATH))
        return json.loads(CACHE_PATH.read_text())

    log_event(logger, "downloading catalog", url=CATALOG_URL)
    with urllib.request.urlopen(CATALOG_URL, timeout=60) as resp:  # noqa: S310
        raw = resp.read()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_bytes(raw)
    catalog = json.loads(raw)
    log_event(logger, "catalog downloaded", bytes=len(raw), path=str(CACHE_PATH))
    return catalog
