"""Transform the OSCAL 800-53 Rev 5 catalog into flat PolicyRecord rows.

Pure functions only (no I/O) so the parsing logic is directly unit-testable.
Withdrawn controls are excluded; control enhancements are emitted as their
own records because they are independently citable requirements.
"""

from __future__ import annotations

import re
from typing import Any

from ..schemas import PolicyRecord

_PARAM_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([^}\s]+)\s*\}\}")


def _param_map(control: dict[str, Any]) -> dict[str, str]:
    """Map OSCAL parameter ids to a readable placeholder text."""
    params: dict[str, str] = {}
    for p in control.get("params", []):
        pid = p.get("id", "")
        if "label" in p:
            text = p["label"]
        elif "select" in p:
            choices = p["select"].get("choice", [])
            text = "selection: " + "; ".join(choices) if choices else "organization-defined selection"
        elif p.get("guidelines"):
            text = p["guidelines"][0].get("prose", "organization-defined value")
        else:
            text = "organization-defined value"
        params[pid] = text
    return params


def _substitute_params(text: str, params: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        return f"[Assignment: {params.get(m.group(1), 'organization-defined value')}]"

    return _PARAM_RE.sub(repl, text)


def _collect_prose(parts: list[dict[str, Any]], names: set[str]) -> list[str]:
    """Recursively collect prose from parts whose name is in `names`.

    Statement items keep their OSCAL labels ("a.", "1.") so the flattened text
    still reads like the official control statement.
    """
    lines: list[str] = []
    for part in parts:
        in_scope = part.get("name") in names or part.get("name") == "item"
        if in_scope and part.get("prose"):
            label = next(
                (p["value"] for p in part.get("props", []) if p.get("name") == "label"),
                None,
            )
            prefix = f"{label} " if label and part.get("name") == "item" else ""
            lines.append(prefix + part["prose"])
        if part.get("parts") and (in_scope or part.get("name") in names):
            lines.extend(_collect_prose(part["parts"], names))
    return lines


def _control_label(control: dict[str, Any]) -> str:
    """Human identifier like 'AC-2(1)': the label prop without an OSCAL class."""
    labels = [p for p in control.get("props", []) if p.get("name") == "label"]
    for p in labels:
        if "class" not in p:
            return p["value"]
    return labels[0]["value"] if labels else control.get("id", "").upper()


def _is_withdrawn(control: dict[str, Any]) -> bool:
    return any(
        p.get("name") == "status" and p.get("value") == "withdrawn"
        for p in control.get("props", [])
    )


def control_to_record(
    control: dict[str, Any], family: str, parent_title: str | None = None
) -> PolicyRecord | None:
    """Convert one OSCAL control (or enhancement) to a PolicyRecord."""
    if _is_withdrawn(control):
        return None

    params = _param_map(control)
    statement = _collect_prose(control.get("parts", []), {"statement"})
    discussion = _collect_prose(control.get("parts", []), {"guidance", "discussion"})

    description = "\n".join(statement).strip()
    if discussion:
        description += "\n\nDiscussion: " + " ".join(discussion).strip()
    description = _substitute_params(description, params).strip()
    if not description:
        return None

    title = control.get("title", "").strip()
    if parent_title and title:
        title = f"{parent_title} — {title}"

    return PolicyRecord(
        # Azure AI Search keys allow only letters, digits, _, - and =.
        id=control["id"].replace(".", "_"),
        control_id=_control_label(control),
        title=title,
        description=description,
        category=family,
    )


def transform_catalog(catalog: dict[str, Any]) -> list[PolicyRecord]:
    """Flatten the full OSCAL catalog into PolicyRecords (controls + enhancements)."""
    records: list[PolicyRecord] = []
    for group in catalog["catalog"]["groups"]:
        family = group["title"]
        for control in group.get("controls", []):
            record = control_to_record(control, family)
            if record:
                records.append(record)
            for enhancement in control.get("controls", []):
                enh_record = control_to_record(
                    enhancement, family, parent_title=control.get("title")
                )
                if enh_record:
                    records.append(enh_record)
    return records
