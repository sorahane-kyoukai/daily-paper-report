"""Embedding-based semantic scorer for topic matching.

Uses fastembed (ONNX-based) to compute semantic similarity between
story text and configured topic descriptions. Falls back gracefully
when fastembed is not installed.
"""

from __future__ import annotations

import structlog

from src.features.config.schemas.topics import TopicConfig


logger = structlog.get_logger()

try:
    import numpy as np
    from fastembed import TextEmbedding

    _FASTEMBED_AVAILABLE = True
except ImportError:
    _FASTEMBED_AVAILABLE = False

# Lightweight model: 384 dimensions, ~50 MB ONNX
_DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def is_available() -> bool:
    """Check if fastembed is installed and usable."""
    return _FASTEMBED_AVAILABLE


class SemanticScorer:
    """Scores text against topic descriptions using embedding similarity.

    Pre-computes topic embeddings on initialization. For each story,
    computes the maximum cosine similarity to any topic embedding and
    returns a weighted score when it exceeds a configurable threshold.

    Requires ``fastembed`` and ``numpy`` as optional dependencies.
    """

    def __init__(
        self,
        topics: list[TopicConfig],
        *,
        model_name: str = _DEFAULT_MODEL,
        similarity_threshold: float = 0.35,
    ) -> None:
        """Initialize the semantic scorer.

        Args:
            topics: Topic configurations (name + keywords used to build
                    natural-language descriptions for embedding).
            model_name: fastembed model identifier.
            similarity_threshold: Minimum cosine similarity to count as
                                  a semantic match.

        Raises:
            RuntimeError: If fastembed is not installed.
        """
        if not _FASTEMBED_AVAILABLE:
            msg = (
                "fastembed is required for semantic scoring. "
                "Install with: uv add fastembed"
            )
            raise RuntimeError(msg)

        self._threshold = similarity_threshold
        self._model = TextEmbedding(model_name=model_name)
        self._topic_names: list[str] = []
        self._topic_weights: list[float] = []

        # Build natural-language descriptions from topic configs
        descriptions = self._build_topic_descriptions(topics)

        # Pre-compute topic embeddings (one vector per topic)
        self._topic_embeddings = np.array(list(self._model.passage_embed(descriptions)))

        logger.info(
            "semantic_scorer_initialized",
            model=model_name,
            topics=len(topics),
            embedding_dim=self._topic_embeddings.shape[1],
        )

    def _build_topic_descriptions(self, topics: list[TopicConfig]) -> list[str]:
        """Build embedding-friendly descriptions from topic configs.

        Combines topic name and keywords into a single descriptive
        sentence suitable for passage embedding.

        Args:
            topics: Topic configurations.

        Returns:
            List of description strings, one per topic.
        """
        descriptions: list[str] = []
        for topic in topics:
            self._topic_names.append(topic.name)
            self._topic_weights.append(topic.boost_weight)
            keywords_str = ", ".join(topic.keywords[:10])
            desc = f"{topic.name}: {keywords_str}"
            descriptions.append(desc)
        return descriptions

    def score_text(self, text: str) -> tuple[float, str | None]:
        """Compute semantic similarity score for text against all topics.

        Args:
            text: Story title + abstract text to score.

        Returns:
            Tuple of (best_similarity, matched_topic_name).
            Returns (0.0, None) if no topic exceeds the threshold.
        """
        if not text.strip():
            return 0.0, None

        # Embed the story text
        text_embedding = np.array(list(self._model.query_embed([text])))[0]

        # Compute cosine similarities (embeddings are pre-normalized)
        similarities = self._topic_embeddings @ text_embedding

        best_idx = int(np.argmax(similarities))
        best_sim = float(similarities[best_idx])

        if best_sim < self._threshold:
            return 0.0, None

        return best_sim, self._topic_names[best_idx]

    def score_text_weighted(
        self,
        text: str,
        weight: float,
        *,
        max_topics: int = 3,
    ) -> float:
        """Compute weighted semantic score for a story.

        Uses the top-k matching topics (by similarity) to avoid inflated
        scores when many topics share vocabulary with a paper. Only topics
        exceeding the similarity threshold are considered.

        Args:
            text: Story title + abstract text.
            weight: Global semantic_match_weight multiplier.
            max_topics: Maximum number of top-matching topics to sum.

        Returns:
            Weighted semantic score (0.0 if below threshold).
        """
        if not text.strip():
            return 0.0

        text_embedding = np.array(list(self._model.query_embed([text])))[0]

        similarities = self._topic_embeddings @ text_embedding

        # Collect (similarity, boost_weight) for topics above threshold
        above_threshold = [
            (float(sim), self._topic_weights[idx])
            for idx, sim in enumerate(similarities)
            if sim >= self._threshold
        ]

        if not above_threshold:
            return 0.0

        # Use only the top-k topics by similarity to prevent score inflation
        above_threshold.sort(key=lambda x: -x[0])
        top_matches = above_threshold[:max_topics]

        total = sum(sim * boost for sim, boost in top_matches)
        return total * weight
