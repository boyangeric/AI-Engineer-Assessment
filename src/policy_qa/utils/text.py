"""Generic text processing helpers."""

from __future__ import annotations

import re

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize_words(text: str) -> set[str]:
    """Lowercase a string and return its set of alphanumeric word tokens."""
    return set(_WORD_RE.findall(text.lower()))


def normalize_control_id(control_id: str) -> str:
    """Canonical form of a control identifier for matching, e.g. 'ac-2 ' -> 'AC-2'.

    Citation validation and grounding checks must agree on this normalization,
    so both call here rather than uppercasing ad hoc.
    """
    return control_id.strip().upper()


def escape_untrusted(text: str) -> str:
    """XML-escape untrusted text destined for an LLM prompt.

    Retrieved index content is delimited with XML-style tags so the model can
    tell data from instructions; escaping angle brackets means the content can
    never close its own delimiter or forge a new one (prompt-injection
    breakout). `&` is escaped first so the entities themselves round-trip.
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(value: str) -> str:
    return escape_untrusted(value).replace('"', "&quot;")


def wrap_untrusted_document(
    index: int, control_id: str, title: str, category: str, content: str
) -> str:
    """Wrap one retrieved chunk in a `<document>` delimiter for prompt use.

    Every field originates from the search index and is therefore untrusted;
    all of it is escaped so nothing inside can terminate the wrapper.
    """
    return (
        f'<document index="{index}" control_id="{_escape_attr(control_id)}" '
        f'title="{_escape_attr(title)}" family="{_escape_attr(category)}">\n'
        f"{escape_untrusted(content)}\n"
        f"</document>"
    )
