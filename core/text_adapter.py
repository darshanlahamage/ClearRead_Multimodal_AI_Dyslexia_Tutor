"""
Text Adapter + Micro-Drill Generator
------------------------------------
Uses Nova 2 Lite to:
  1. Rewrite a passage adapted to a learner's specific error patterns
  2. Generate 3 targeted micro-drills

Uses boto3.client("bedrock-runtime").converse()
Model: us.amazon.nova-2-lite-v1:0
"""

import json
import logging
import re
import boto3

from config.settings import AWS_REGION, LITE_MODEL_ID

logger = logging.getLogger(__name__)

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


def _parse_json_response(response: dict) -> dict | list | None:
    """
    Extract JSON from a Nova Lite converse() response.
    Strips markdown fences, handles thinking blocks.
    Returns parsed object or None on failure.
    """
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        if block.get("type") == "thinking":
            continue
        if block.get("type") == "text":
            raw = block.get("text", "")
            cleaned = re.sub(r"```json|```", "", raw).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                # Try pulling JSON from within text
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group())
                    except json.JSONDecodeError:
                        pass
                match_list = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if match_list:
                    try:
                        return json.loads(match_list.group())
                    except json.JSONDecodeError:
                        pass
    return None


def generate_adapted_text(passage: dict, profile: dict) -> dict:
    """
    Rewrite a passage adapted to the learner's top error patterns.
    
    Args:
        passage: dict with 'text', 'passage_id', 'title'
        profile: learner error profile dict  
    
    Returns:
        {adapted_text, changes_made, rationale}
    """
    original_text = passage.get("text", "")
    if not original_text:
        return _default_adapted(original_text)

    # Get top 2 error categories by severity
    categories = {}
    for cat in ["phonological_decoding", "visual_tracking", "working_memory", "fluency"]:
        cat_data = profile.get(cat)
        if cat_data:
            categories[cat] = {
                "severity": float(cat_data.get("severity", 0)),
                "patterns": cat_data.get("patterns", []),
            }

    if not categories:
        return _default_adapted(original_text)

    top_cats = sorted(categories.items(), key=lambda x: x[1]["severity"], reverse=True)[:2]

    top_cats_text = "\n".join([
        f"  - {cat}: severity {data['severity']:.1f}, patterns: {data['patterns']}"
        for cat, data in top_cats
    ])

    working_memory_severity = float(profile.get("working_memory", {}).get("severity", 0) if isinstance(profile.get("working_memory"), dict) else 0)
    sentence_instruction = ""
    if working_memory_severity > 6.0:
        sentence_instruction = "\n- IMPORTANT: Break any sentences longer than 10 words into two shorter sentences."

    prompt = f"""You are adapting a reading passage for a learner with dyslexia.

ORIGINAL PASSAGE:
{original_text}

LEARNER'S TOP DIFFICULTY AREAS:
{top_cats_text}

ADAPTATION RULES:
- For phonological difficulty with specific patterns (e.g., bl_cluster): replace words containing those phoneme patterns with simpler synonyms when possible
- Preserve the complete meaning of the passage
- Keep vocabulary age-appropriate (this is a school-age reader){sentence_instruction}
- Only make necessary changes — do not over-simplify

Return ONLY a valid JSON object with this exact structure (no markdown, no explanation):
{{
  "adapted_text": "The full adapted passage here",
  "changes_made": [
    {{"original": "word_that_was_changed", "adapted": "replacement_word", "reason": "brief reason"}}
  ],
  "rationale": "One sentence summary of the adaptations made"
}}"""

    try:
        response = _bedrock.converse(
            modelId=LITE_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        result = _parse_json_response(response)
        if result and isinstance(result, dict) and "adapted_text" in result:
            logger.info(f"Adapted text generated: {len(result.get('changes_made', []))} changes")
            return result
    except Exception as e:
        logger.error(f"generate_adapted_text failed: {e}")

    return _default_adapted(original_text)


def generate_micro_drills(profile: dict) -> list:
    """
    Generate 3 targeted micro-drills based on the learner's top error patterns.
    
    Returns list of 3 drill dicts:
        [{type, instruction, words, estimated_seconds}]
    """
    # Get top 2 categories
    categories = {}
    for cat in ["phonological_decoding", "visual_tracking", "working_memory", "fluency"]:
        cat_data = profile.get(cat)
        if cat_data:
            categories[cat] = {
                "severity": float(cat_data.get("severity", 0)),
                "patterns": cat_data.get("patterns", []),
            }

    if not categories:
        return _default_drills()

    top_cats = sorted(categories.items(), key=lambda x: x[1]["severity"], reverse=True)[:2]
    top_cats_text = "\n".join([
        f"  - {cat}: severity {data['severity']:.1f}, patterns: {data['patterns']}"
        for cat, data in top_cats
    ])

    prompt = f"""You are designing practice drills for a learner with dyslexia.

LEARNER'S TOP DIFFICULTY AREAS:
{top_cats_text}

TASK: Generate exactly 3 micro-drills targeting these difficulties.
Each drill must be a different type:
  - phoneme_isolation: say individual sounds one at a time, then blend them together
  - fluency_phrase: read a short phrase smoothly multiple times
  - word_building: build a word step-by-step from its sound components (use format "bl+ue" etc.)

Instructions must be:
- In simple, warm, everyday language (this is for a child or adult learning to read)
- Specific and actionable
- Positive and encouraging

Return ONLY a valid JSON array of exactly 3 drills (no markdown, no explanation):
[
  {{
    "type": "phoneme_isolation",
    "instruction": "Written instruction in plain language",
    "words": ["word1", "word2", "word3"],
    "estimated_seconds": 60
  }},
  {{
    "type": "fluency_phrase",
    "instruction": "Written instruction in plain language",
    "words": ["phrase word 1", "phrase word 2"],
    "estimated_seconds": 45
  }},
  {{
    "type": "word_building",
    "instruction": "Written instruction in plain language",
    "words": ["bl+ue", "bl+ack", "bl+end"],
    "estimated_seconds": 90
  }}
]"""

    try:
        response = _bedrock.converse(
            modelId=LITE_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
        )
        result = _parse_json_response(response)
        if result and isinstance(result, list) and len(result) >= 3:
            logger.info(f"Generated {len(result)} micro-drills")
            return result[:3]
    except Exception as e:
        logger.error(f"generate_micro_drills failed: {e}")

    return _default_drills()


def _default_adapted(original: str) -> dict:
    return {
        "adapted_text": original,
        "changes_made": [],
        "rationale": "No adaptation applied (Nova Lite unavailable).",
    }


def _default_drills() -> list:
    return [
        {
            "type": "phoneme_isolation",
            "instruction": "Say each sound slowly: b... l... ue. Then put them together: blue!",
            "words": ["blue", "black", "blend"],
            "estimated_seconds": 60,
        },
        {
            "type": "fluency_phrase",
            "instruction": "Read this phrase smoothly 3 times in a row without stopping.",
            "words": ["the black cat", "sat on the mat"],
            "estimated_seconds": 45,
        },
        {
            "type": "word_building",
            "instruction": "Build each word by saying its parts and joining them together.",
            "words": ["bl+ue", "bl+ack", "bl+end"],
            "estimated_seconds": 90,
        },
    ]
