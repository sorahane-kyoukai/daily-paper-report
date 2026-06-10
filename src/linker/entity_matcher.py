"""Entity matching for items based on keywords."""

import json
import re
from dataclasses import dataclass, field

from src.features.config.schemas.entities import EntityConfig
from src.features.store.models import Item


@dataclass
class EntityMatch:
    """Result of entity matching for an item.

    Attributes:
        entity_id: ID of the matched entity.
        entity_name: Name of the matched entity.
        matched_keywords: Keywords that matched.
        match_score: Score based on number and quality of matches.
    """

    entity_id: str
    entity_name: str
    matched_keywords: list[str] = field(default_factory=list)
    match_score: float = 0.0


def _build_search_text(item: Item) -> str:
    """Build searchable text from item title, authors, and raw_json."""
    search_text = item.title.lower()
    try:
        raw = json.loads(item.raw_json)
        if abstract := raw.get("abstract"):
            search_text += f" {abstract.lower()}"
        if description := raw.get("description"):
            search_text += f" {description.lower()}"
        if authors := raw.get("authors"):
            if isinstance(authors, list):
                search_text += f" {' '.join(str(a) for a in authors).lower()}"
            elif isinstance(authors, str):
                search_text += f" {authors.lower()}"
    except (json.JSONDecodeError, KeyError):
        pass
    return search_text


def _find_matching_keywords(terms: list[str], search_text: str) -> list[str]:
    """Find terms that match in search_text using word boundary matching."""
    matched: list[str] = []
    for term in terms:
        pattern = rf"\b{re.escape(term.lower())}\b"
        if re.search(pattern, search_text, re.IGNORECASE):
            matched.append(term)
    return matched


def _calculate_match_score(matched_keywords: list[str], title: str) -> float:
    """Calculate match score with title boost."""
    score = float(len(matched_keywords))
    title_lower = title.lower()
    for kw in matched_keywords:
        if kw.lower() in title_lower:
            score += 1.0
    return score


def _match_single_entity(
    entity: EntityConfig, search_text: str, title: str
) -> EntityMatch | None:
    """Match a single entity against search text."""
    matched_keywords = _find_matching_keywords(entity.keywords, search_text)
    matched_keywords.extend(_find_matching_keywords(entity.aliases, search_text))

    if not matched_keywords:
        return None

    return EntityMatch(
        entity_id=entity.id,
        entity_name=entity.name,
        matched_keywords=matched_keywords,
        match_score=_calculate_match_score(matched_keywords, title),
    )


def match_item_to_entities(
    item: Item,
    entities: list[EntityConfig],
) -> list[EntityMatch]:
    """Match an item to entities based on keywords.

    Matches against title and raw_json content.

    Args:
        item: Item to match.
        entities: List of entity configurations.

    Returns:
        List of EntityMatch results, sorted by match_score descending.
    """
    search_text = _build_search_text(item)
    matches: list[EntityMatch] = []

    for entity in entities:
        match = _match_single_entity(entity, search_text, item.title)
        if match:
            matches.append(match)

    matches.sort(key=lambda m: m.match_score, reverse=True)
    return matches


def get_primary_entity(matches: list[EntityMatch]) -> str | None:
    """Get the primary entity ID from matches.

    Args:
        matches: List of entity matches.

    Returns:
        Primary entity ID or None if no matches.
    """
    if not matches:
        return None
    return matches[0].entity_id


def get_all_entity_ids(matches: list[EntityMatch]) -> list[str]:
    """Get all matched entity IDs.

    Args:
        matches: List of entity matches.

    Returns:
        List of entity IDs.
    """
    return [m.entity_id for m in matches]
