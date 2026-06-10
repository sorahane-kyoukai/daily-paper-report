"""Prompt templates for LLM-powered Traditional Chinese translation."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence


SYSTEM_INSTRUCTION = (
    "You are a professional translator specializing in AI/ML academic papers. "
    "Translate to Traditional Chinese (\u7e41\u9ad4\u4e2d\u6587). "
    "Preserve technical terms, model names, acronyms, and proper nouns in English. "
    "For example: 'Transformer', 'GPT-4', 'RLHF', 'fine-tuning' should remain in English. "
    "Maintain the academic tone and precision of the original text. "
    "Respond ONLY with a JSON array, no markdown fences or extra text."
)

_BATCH_TEMPLATE = """## Stories to Translate

{stories_section}

## Output Format
Respond with a JSON array. Each element must have these fields:
- "id": the story_id exactly as given
- "title_zh": the title translated to Traditional Chinese
- "summary_zh": a richer Traditional Chinese summary, 2-4 complete sentences and about 220-320 Chinese characters when the source summary has enough information (empty string if no summary)

Keep technical terms, model names, acronyms, and proper nouns in English within the Chinese text.
Do not use the numbered-list index as "id"; copy the bracketed story_id exactly.
Use Chinese full stops "。" between sentences so the frontend can display readable paragraphs.
Do not translate the full abstract verbatim; explain the key problem, method, result or claimed benefit, and why it may matter.

Example:
[{{"id": "example-1", "title_zh": "\u57fa\u65bc Transformer \u7684\u65b0\u578b\u591a\u6a21\u614b\u5b78\u7fd2\u67b6\u69cb", "summary_zh": "\u672c\u6587\u805a\u7126\u591a\u6a21\u614b\u8cc7\u6599\u5728\u8a13\u7df4\u8207\u63a8\u8ad6\u6642\u7684\u8868\u5fb5\u5c0d\u9f4a\u554f\u984c\uff0c\u63d0\u51fa\u4e86\u7d50\u5408 Transformer \u8207 contrastive learning \u7684\u65b0\u67b6\u69cb\u3002\u4f5c\u8005\u5f37\u8abf\u6b64\u65b9\u6cd5\u80fd\u964d\u4f4e\u8de8\u6a21\u614b\u566a\u8072\uff0c\u4e26\u5728\u591a\u500b\u8996\u89ba\u8a9e\u8a00\u4efb\u52d9\u4e0a\u6539\u5584\u6e96\u78ba\u7387\u3002\u503c\u5f97\u95dc\u6ce8\u7684\u662f\uff0c\u5b83\u4e5f\u63d0\u4f9b\u4e86\u53ef\u64f4\u5c55\u7684\u6d88\u878d\u8a2d\u8a08\uff0c\u4fbf\u65bc\u6bd4\u8f03\u4e0d\u540c\u6a21\u614b\u5c0d\u6700\u7d42\u8868\u73fe\u7684\u8ca2\u737b\u3002"}}]
"""

CURRENT_TRANSLATION_PROMPT_VERSION = (
    "sha256:"
    + hashlib.sha256(f"{SYSTEM_INSTRUCTION}\n{_BATCH_TEMPLATE}".encode()).hexdigest()[
        :16
    ]
)


def build_translation_prompt(stories: Sequence[Mapping[str, object]]) -> str:
    """Build a batch translation prompt for multiple stories.

    Args:
        stories: Story dicts with at minimum 'story_id', 'title',
                 and optionally 'summary' fields.

    Returns:
        Formatted prompt string for translation.
    """
    lines: list[str] = []
    for i, story in enumerate(stories, 1):
        story_id = story.get("story_id", "")
        title = story.get("title", "")
        summary = story.get("summary", "") or ""
        summary_part = f"\n   Summary: {summary}" if summary else ""
        lines.append(f"{i}. [{story_id}] Title: {title}{summary_part}")

    stories_section = "\n".join(lines)

    return _BATCH_TEMPLATE.format(stories_section=stories_section)
