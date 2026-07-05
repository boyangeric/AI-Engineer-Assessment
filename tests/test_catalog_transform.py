"""Tests for the OSCAL -> PolicyRecord transformation."""

import pytest

from policy_qa.ingestion.catalog_transform import control_to_record, transform_catalog

SYNTHETIC_CONTROL = {
    "id": "xx-1",
    "title": "Test Control",
    "params": [{"id": "xx-1_prm_1", "label": "organization-defined frequency"}],
    "props": [{"name": "label", "value": "XX-1"}],
    "parts": [
        {
            "name": "statement",
            "parts": [
                {
                    "name": "item",
                    "props": [{"name": "label", "value": "a."}],
                    "prose": "Review the policy {{ insert: param, xx-1_prm_1 }};",
                }
            ],
        },
        {"name": "guidance", "prose": "This is the discussion text."},
    ],
}

WITHDRAWN_CONTROL = {
    "id": "xx-2",
    "title": "Old Control",
    "props": [
        {"name": "label", "value": "XX-2"},
        {"name": "status", "value": "withdrawn"},
    ],
    "parts": [{"name": "statement", "prose": "Something."}],
}


def test_control_to_record_parses_statement_and_discussion():
    record = control_to_record(SYNTHETIC_CONTROL, family="Test Family")
    assert record is not None
    assert record.control_id == "XX-1"
    assert record.category == "Test Family"
    assert "a. Review the policy" in record.description
    assert "[Assignment: organization-defined frequency]" in record.description
    assert "Discussion: This is the discussion text." in record.description


def test_withdrawn_controls_are_excluded():
    assert control_to_record(WITHDRAWN_CONTROL, family="Test Family") is None


def test_search_safe_ids():
    enhancement = {**SYNTHETIC_CONTROL, "id": "xx-1.2"}
    record = control_to_record(enhancement, family="F", parent_title="Parent")
    assert record is not None
    assert record.id == "xx-1_2"
    assert record.title.startswith("Parent — ")


def test_full_catalog_meets_record_minimum():
    """The real 800-53 Rev 5 catalog must yield >= 500 complete records."""
    pytest.importorskip("urllib.request")
    from policy_qa.ingestion.catalog_download import download_catalog

    records = transform_catalog(download_catalog())
    assert len(records) >= 500
    for record in records:
        assert record.id and record.title and record.description and record.category
