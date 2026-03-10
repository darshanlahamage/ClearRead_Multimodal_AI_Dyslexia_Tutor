"""
Nova Multimodal Embeddings
--------------------------
Converts text into a 1024-dimensional vector using Amazon Nova 2 Multimodal Embeddings.
Used for semantic similarity search between learner profiles and reading content.

Model: amazon.nova-2-multimodal-embeddings-v1:0
Region: us-east-1
"""

import json
import logging
import boto3

from config.settings import AWS_REGION, EMBEDDINGS_MODEL_ID

logger = logging.getLogger(__name__)

# Must be us-east-1 — Nova Embeddings is not available in other regions
_bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")


def embed_text(text: str) -> list[float]:
    """
    Embed a text string into a 1024-dimensional float vector.
    
    Args:
        text: any text string (profile description or passage text)
    
    Returns:
        list of 1024 floats (the embedding vector)
    """
    body = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": 1024,
            "text": {
                "truncationMode": "END",
                "value": text
            }
        }
    }

    try:
        response = _bedrock.invoke_model(
            modelId=EMBEDDINGS_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        # Response format: {"embeddings": [{"embeddingType": "TEXT", "embedding": [...1024 floats]}]}
        vector = result["embeddings"][0]["embedding"]
        logger.debug(f"Embedded text ({len(text)} chars) → {len(vector)}-dim vector")
        return vector
    except Exception as e:
        logger.error(f"embed_text failed: {e}")
        raise


def profile_to_text(profile: dict) -> str:
    """
    Convert a learner profile dict to a human-readable diagnostic description
    suitable for embedding. This text places learners with similar reading
    challenges close together in vector space.
    
    Example output:
        Grade 2 reader. Phonological decoding difficulty: severity 7.2,
        bl_cluster and str_cluster patterns. Fluency: severity 4.8.
        Working memory: severity 3.0. Visual tracking: severity 2.1.
        Average reading speed 55 WPM. 5 sessions completed.
    
    Args:
        profile: learner profile dict from DynamoDB
    
    Returns:
        Descriptive string for embedding
    """
    difficulty = profile.get("current_difficulty_band", "unknown").replace("_", " ")
    session_count = profile.get("session_count", 0)

    # Get recent WPM from last session summary if available
    recent = profile.get("recent_sessions", [])
    wpm_str = ""
    if recent and isinstance(recent, list):
        last = recent[-1] if isinstance(recent[-1], dict) else {}
        wpm = last.get("words_per_minute", 0)
        if wpm:
            wpm_str = f" Average reading speed {float(wpm):.0f} WPM."

    # Build error category descriptions
    cat_descriptions = []
    for cat, label in [
        ("phonological_decoding", "Phonological decoding"),
        ("visual_tracking", "Visual tracking"),
        ("working_memory", "Working memory"),
        ("fluency", "Fluency"),
    ]:
        cat_data = profile.get(cat)
        if cat_data and isinstance(cat_data, dict):
            sev = float(cat_data.get("severity", 0))
            pats = cat_data.get("patterns", [])
            pats_str = f", {' and '.join(pats)} patterns" if pats else ""
            cat_descriptions.append(f"{label}: severity {sev:.1f}{pats_str}")

    cats_text = ". ".join(cat_descriptions) if cat_descriptions else "No error profile yet"

    text = (
        f"{difficulty.title()} reader. "
        f"{cats_text}."
        f"{wpm_str}"
        f" {session_count} session{'s' if session_count != 1 else ''} completed."
    )

    logger.debug(f"profile_to_text: {text}")
    return text
