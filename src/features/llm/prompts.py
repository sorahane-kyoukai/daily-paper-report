"""Prompt templates for LLM paper relevance evaluation."""

from src.features.config.schemas.topics import TopicConfig
from src.linker.models import Story


SYSTEM_INSTRUCTION = (
    "You are an expert AI/ML research curator for practitioners and researchers "
    "focused on large language models, AI agents, multi-agent systems, reasoning, "
    "alignment, safety, and core ML methodology. "
    "Your task is to evaluate papers on BOTH topical relevance AND research quality.\n\n"
    "MANDATORY EXCLUSIONS - Score 0.0-0.2 regardless of quality:\n"
    "- Single-cell biology / genomics foundation models (scGPT, Geneformer, scBERT)\n"
    "- Pure computer vision WITHOUT language component (image classification, segmentation)\n"
    "- Pure robotics manipulation WITHOUT language/agent methodology\n"
    "- Pure audio/speech processing WITHOUT LLM integration\n"
    "- Pure diffusion models for image/video generation WITHOUT language\n"
    "- Medical imaging, EEG analysis, protein structure prediction\n"
    "- Any 'foundation model' that is NOT a language model\n"
    "These are OUT OF SCOPE even if well-written or from top labs.\n\n"
    "Score HIGH (0.85+) for papers that: "
    "(a) advance LLM/agent capabilities or training methodology, "
    "(b) introduce novel architectures for LANGUAGE models, "
    "(c) propose new safety/alignment/evaluation methods with empirical evidence, "
    "(d) provide reusable frameworks, benchmarks, or open-source tools for LLM/agents, "
    "(e) reveal mechanistic insights about how LANGUAGE models work (interpretability), "
    "(f) come from top labs with strong empirical results ON LANGUAGE TASKS.\n\n"
    "Score MEDIUM (0.5-0.7) for: solid incremental work on LLM/agents, useful NLP datasets, "
    "application papers that contribute novel LLM methodology.\n\n"
    "Score LOW (0.0-0.3) for papers that merely USE LLMs/agents as a black-box tool "
    "for domain tasks WITHOUT contributing new AI/ML methodology.\n\n"
    "CRITICAL: Use the FULL score range. Not everything deserves 0.8+. "
    "Be strict: only truly important LLM/agent papers get 0.85+. "
    "Domain applications get 0.1-0.3. Mediocre work gets 0.4-0.6.\n\n"
    "Respond ONLY with a JSON array, no markdown fences or extra text."
)

_BATCH_TEMPLATE = """## Topics of Interest
{topics_section}

## Papers to Evaluate
{papers_section}

## Scoring Rubric
Rate each paper considering BOTH relevance and quality:

- **0.85-1.0**: Breakthrough or highly novel work. New architectures, paradigm-shifting methods,
  major advances in LLM/agent/reasoning/safety/training. Papers from top venues
  (ICLR, NeurIPS, ICML, ACL) or leading labs. Examples: novel RL algorithms for LLM training,
  new agent frameworks with strong benchmarks, safety findings that change how we think about
  alignment, mechanistic interpretability discoveries, new training paradigms.
- **0.7-0.84**: Significant contribution with clear novelty. New training techniques,
  meaningful benchmark results, practical frameworks, open-source tools, production-scale
  deployment insights, theoretical advances explaining model behavior, new evaluation
  methodologies, cross-model safety findings with empirical evidence.
- **0.5-0.69**: Solid work with some novelty. Useful ablations, new datasets, meaningful
  improvements on existing approaches, insightful analysis, good survey papers.
- **0.3-0.49**: Incremental or narrow. Applies existing methods to specific domains without
  AI/ML methodological novelty, or provides minor improvements without new insights.
- **0.1-0.29**: Domain applications or out-of-scope areas:
  * Papers that USE LLMs/transformers/agents as tools for domain tasks
  * Single-cell foundation models (scGPT, Geneformer) - these are biology, not LLM research
  * Pure computer vision without language (image segmentation, object detection)
  * Pure robotics manipulation without language/agent methodology
  * Medical imaging, EEG analysis, protein structure, drug discovery
  * Diffusion models for pure image/video generation without language
  Even if the title contains "LLM", "foundation model", or "agent", if the contribution
  is in the domain rather than in AI/ML methodology for language, score here.
- **0.0-0.09**: Completely irrelevant. Pure domain science with no AI connection.

CONCRETE LOW-SCORE EXAMPLES (score these 0.1-0.2):
- "scGPT: Single-cell foundation model" → 0.15 (biology domain, not language model)
- "Diffusion for image generation" → 0.2 (CV domain, no language component)
- "Robot manipulation with visual feedback" → 0.15 (robotics, no language/agent)
- "EEG-based emotion recognition with transformers" → 0.1 (medical domain)
- "Protein structure prediction" → 0.1 (biology domain)

CRITICAL SCORING RULES:
1. Keyword density does NOT equal quality. A paper mentioning "LLM" 20 times can still be 0.2.
2. THE DOMAIN TEST: Ask "Does this paper teach AI/ML researchers how to build BETTER models,
   agents, or systems?" If the answer is mainly about the domain, score 0.1-0.29.
   Examples: "LLM for medical diagnosis" = domain (0.2). "Improving attention for long
   sequences" = method (0.7+). "Agent safety benchmark across 6 models" = method (0.8+).
3. TOP-VENUE ACCEPTANCE (NeurIPS, ICML, ICLR, ACL, CVPR oral/spotlight) adds +0.1.
4. OPEN-SOURCE code/models with the paper adds +0.05.
5. REUSABLE INSIGHTS: Papers with findings that generalize beyond one task score higher.
   "Training technique X improves 3 different benchmarks" (0.8) vs "Applying X to task Y" (0.3).

## Output Format
Respond with a JSON array. Each element must have these fields:
- "id": the story_id exactly as given
- "score": float from 0.0 to 1.0 using the rubric above
- "rationale": one sentence explaining the score
- "topics": list of matched topic names (empty list if none)

Example:
[{{"id": "example-1", "score": 0.85, "rationale": "Novel RLHF variant with strong empirical results, accepted at ICLR.", "topics": ["Alignment & RLHF", "Large Language Models"]}}]
"""


def build_topics_section(topics: list[TopicConfig]) -> str:
    """Build the topics section of the prompt.

    Args:
        topics: Configured topic definitions with keywords.

    Returns:
        Formatted topics section string.
    """
    lines: list[str] = []
    for topic in topics:
        keywords_str = ", ".join(topic.keywords)
        lines.append(f"- **{topic.name}**: {keywords_str}")
    return "\n".join(lines)


def _extract_abstract(story: Story) -> str:
    """Extract abstract text from a story's raw items.

    Args:
        story: Story to extract abstract from.

    Returns:
        Abstract text or empty string if not found.
    """
    import json

    for item in story.raw_items:
        try:
            raw = json.loads(item.raw_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for field_name in ("abstract_snippet", "summary", "readme_summary"):
            value = raw.get(field_name)
            if isinstance(value, str) and value:
                return value
    return ""


def build_batch_prompt(
    stories: list[Story],
    topics: list[TopicConfig],
) -> str:
    """Build a batch evaluation prompt for multiple stories.

    Args:
        stories: Stories to evaluate (up to batch size).
        topics: Configured topic definitions.

    Returns:
        Formatted prompt string.
    """
    topics_section = build_topics_section(topics)

    paper_lines: list[str] = []
    for i, story in enumerate(stories, 1):
        abstract = _extract_abstract(story)
        abstract_part = f" | Abstract: {abstract}" if abstract else ""
        paper_lines.append(
            f"{i}. [{story.story_id}] Title: {story.title}{abstract_part}"
        )

    papers_section = "\n".join(paper_lines)

    return _BATCH_TEMPLATE.format(
        topics_section=topics_section,
        papers_section=papers_section,
    )
