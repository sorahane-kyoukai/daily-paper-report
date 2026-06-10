"""Shared JSON parsing utilities for LLM response handling.

Provides robust parsing of JSON arrays from LLM output, handling
common issues like markdown fences, invalid escape sequences, and
extra text after the JSON payload.
"""

from __future__ import annotations

import json
import re


def fix_escape_sequences(text: str) -> str:
    """Fix invalid JSON escape sequences in LLM output.

    LLMs sometimes produce backslash sequences like ``\\_`` that are
    invalid in JSON strings. This replaces lone backslashes with
    double-backslashes where they don't form a valid JSON escape.

    Args:
        text: Raw text potentially containing invalid escapes.

    Returns:
        Text with invalid escape sequences fixed.
    """
    return re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', r"\\\\", text)


def try_parse_json_array(text: str) -> list[dict[str, object]] | None:
    """Try to parse text as a JSON array, with escape-sequence fallback.

    Args:
        text: Raw JSON text from LLM response.

    Returns:
        Parsed list if successful, None otherwise.
    """
    try:
        entries = json.loads(text)
        if isinstance(entries, list):
            return entries
    except json.JSONDecodeError:
        pass

    try:
        entries = json.loads(fix_escape_sequences(text))
        if isinstance(entries, list):
            return entries
    except json.JSONDecodeError:
        pass

    return None


def extract_first_json_array(text: str) -> str | None:
    """Extract the first complete ``[...]`` block from text.

    Handles the common "Extra data" error where the LLM appends text
    after the JSON array.

    Args:
        text: Raw text potentially containing a JSON array.

    Returns:
        Extracted JSON array string, or None if no bracket pair found.
    """
    depth = 0
    start = text.find("[")
    if start == -1:
        return None

    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def json_candidates(text: str) -> list[str]:
    """Generate candidate JSON strings to try parsing.

    Returns the full text first, then the first extracted array block
    if the full text fails.

    Args:
        text: Raw text from LLM response.

    Returns:
        List of candidate strings to attempt parsing.
    """
    candidates = [text]
    extracted = extract_first_json_array(text)
    if extracted and extracted != text:
        candidates.append(extracted)
    return candidates


def strip_markdown_fences(text: str) -> str:
    """Strip markdown code fences from LLM response text.

    Args:
        text: Raw text potentially wrapped in code fences.

    Returns:
        Text with code fences removed.
    """
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
    return text
