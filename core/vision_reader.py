"""
Vision Reader — Nova 2 Lite Image Understanding
-------------------------------------------------
Sends an image to Nova 2 Lite via the Converse API with image content block.
Nova Vision OCRs text, identifies objects, and generates a personalized
reading passage based on what's in the photo — adapted to the student's level.

This creates the full multimodal loop:
  Image → Text (Nova Vision) → Speech (Nova Sonic) → Analysis (Nova Lite)
"""

import json
import logging
import re
import base64
import boto3

from config.settings import AWS_REGION, LITE_MODEL_ID

logger = logging.getLogger(__name__)
_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)


VISION_PROMPT = """You are Coach Nova, an AI reading tutor for children with dyslexia.

A student just uploaded a photo of something in their world. Your job:

1. DESCRIBE what you see in the image (2-3 sentences).
2. EXTRACT any text visible in the image (OCR). If no text, say "No text found."
3. GENERATE a short reading passage (3-5 sentences) INSPIRED by what's in the image.
   - The passage must be at a {grade_level} reading level
   - Use simple, clear sentences
   - Include vocabulary words from the image
   - If the student has specific weak phoneme patterns ({weak_patterns}), try to include words with those sounds

{profile_instructions}

Return ONLY a JSON object with this EXACT structure:
{{
  "scene_description": "A colorful cereal box sits on a kitchen table...",
  "detected_text": "Frosted Flakes - They're Grrreat!",
  "generated_passage": "Tony the Tiger loves his breakfast. He eats cereal every morning. The cereal box is bright orange and blue. Tony says the flakes taste great!",
  "vocabulary_words": ["breakfast", "cereal", "bright", "morning"],
  "difficulty_band": "grade_1"
}}"""


def analyze_image(image_bytes: bytes, learner_profile: dict = None, media_type: str = "image/jpeg") -> dict:
    """
    Send an image to Nova 2 Lite for vision understanding.
    Returns scene description, OCR text, and a generated reading passage.
    """
    profile = learner_profile or {}

    # Determine grade level and weak patterns from profile
    difficulty = profile.get("current_difficulty_band", "grade_1")
    grade_level = difficulty.replace("_", " ").replace("grade ", "Grade ")

    weak_patterns = []
    phon = profile.get("phonological_decoding", {})
    if isinstance(phon, dict):
        weak_patterns = phon.get("patterns", [])

    profile_instructions = ""
    if weak_patterns:
        profile_instructions = f"The student struggles with these phoneme patterns: {', '.join(weak_patterns)}. Try to include words that practice those sounds."

    prompt_text = VISION_PROMPT.format(
        grade_level=grade_level,
        weak_patterns=", ".join(weak_patterns) if weak_patterns else "none identified yet",
        profile_instructions=profile_instructions,
    )

    # Build the multimodal message with image + text
    try:
        response = _bedrock.converse(
            modelId=LITE_MODEL_ID,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": media_type.split("/")[-1].replace("jpg", "jpeg"),  # ensure jpeg/png/webp
                            "source": {
                                "bytes": image_bytes
                            }
                        }
                    },
                    {
                        "text": prompt_text
                    }
                ]
            }],
        )
    except Exception as e:
        logger.error(f"Nova Vision converse failed: {e}")
        return _fallback_response()

    # Parse content blocks from Nova's response
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    
    for block in content_blocks:
        if "text" in block:
            raw = block["text"]
            
            # Extract JSON from potential Markdown formatting or surrounding text
            start = raw.find('{')
            end = raw.rfind('}')
            
            if start != -1 and end != -1:
                json_str = raw[start:end+1]
                try:
                    result = json.loads(json_str)
                    # Ensure minimum required keys exist
                    if "generated_passage" not in result:
                        result["generated_passage"] = "I see the picture! Let's read this story together."
                    return result
                except json.JSONDecodeError:
                    continue

    logger.warning("Nova Vision parsing failed, falling back to default response.")
    return _fallback_response()


def _fallback_response() -> dict:
    """Return a sensible fallback if Nova Vision fails."""
    return {
        "scene_description": "I couldn't quite see the image clearly. Let's try a fun story instead!",
        "detected_text": "",
        "generated_passage": "The sun was shining bright today. A little bird sat on a branch and sang a song. The flowers in the garden were red and yellow. It was a beautiful day to read outside!",
        "vocabulary_words": ["shining", "branch", "garden", "beautiful"],
        "difficulty_band": "grade_1",
    }
