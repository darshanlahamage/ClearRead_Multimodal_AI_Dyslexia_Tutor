"""
S3 Vectors Storage
-------------------
Put/query vectors in AWS S3 Vectors service.

IMPORTANT: Uses boto3.client("s3vectors") — a separate client from the standard S3 client.
Methods: put_vectors(), query_vectors()

Two indexes:
  - learner-ability-index: one vector per learner, 1024 dims, Cosine
  - content-library-index: one vector per passage, 1024 dims, Cosine
"""

import logging
import boto3

from config.settings import VECTOR_BUCKET

logger = logging.getLogger(__name__)

# S3 Vectors is a separate service, not standard S3
_s3vectors = boto3.client("s3vectors", region_name="us-east-1")

LEARNER_INDEX = "learner-ability-index"
CONTENT_INDEX = "content-library-index"

# Cosine similarity range for "zone of proximal development"
# similarity = 1 - cosine_distance (S3 Vectors returns distance not similarity)
MIN_SIMILARITY = 0.55
MAX_SIMILARITY = 0.85


def upsert_learner_vector(learner_id: str, vector: list[float], metadata: dict) -> bool:
    """
    Store or update a learner's embedding vector in the learner-ability-index.
    
    Args:
        learner_id: unique learner identifier
        vector: 1024-dim float vector from embed_text()
        metadata: dict with learner_id, difficulty_band, last_updated
    
    Returns:
        True on success, False on failure
    """
    try:
        _s3vectors.put_vectors(
            vectorBucketName=VECTOR_BUCKET,
            indexName=LEARNER_INDEX,
            vectors=[{
                "key": f"learner:{learner_id}",
                "data": {"float32": vector},
                "metadata": metadata,
            }]
        )
        logger.info(f"Upserted learner vector: learner:{learner_id}")
        return True
    except Exception as e:
        logger.error(f"upsert_learner_vector failed: {e}")
        return False


def upsert_content_vector(passage_id: str, vector: list[float], metadata: dict) -> bool:
    """
    Store a passage embedding in the content-library-index.
    
    Args:
        passage_id: e.g. "g2_p001"
        vector: 1024-dim float vector from embed_text()
        metadata: dict with passage_id, title, difficulty_band, target_phoneme_patterns
    
    Returns:
        True on success, False on failure
    """
    try:
        _s3vectors.put_vectors(
            vectorBucketName=VECTOR_BUCKET,
            indexName=CONTENT_INDEX,
            vectors=[{
                "key": f"content:{passage_id}",
                "data": {"float32": vector},
                "metadata": metadata,
            }]
        )
        logger.info(f"Upserted content vector: content:{passage_id}")
        return True
    except Exception as e:
        logger.error(f"upsert_content_vector failed: {e}")
        return False


def query_content_recommendations(
    learner_vector: list[float],
    exclude_passage_id: str = "",
    top_k: int = 5
) -> list[dict]:
    """
    Find the best-matched passages for a learner using semantic similarity.
    
    Filters to the "zone of proximal development":
        similarity 0.55–0.85 (not too easy, not too hard)
    
    Args:
        learner_vector: 1024-dim float vector (learner's current embedding)
        exclude_passage_id: passage the learner just read — don't recommend it again
        top_k: how many candidates to fetch before filtering
    
    Returns:
        List of up to 3 passage dicts: {passage_id, title, difficulty_band, similarity_score}
    """
    try:
        response = _s3vectors.query_vectors(
            vectorBucketName=VECTOR_BUCKET,
            indexName=CONTENT_INDEX,
            queryVector={"float32": learner_vector},
            topK=top_k,
            returnMetadata=True,
            returnDistance=True,
        )
    except Exception as e:
        logger.error(f"query_content_recommendations failed: {e}")
        return []

    matches = response.get("vectors", [])
    results = []

    for match in matches:
        key = match.get("key", "")
        distance = float(match.get("distance", 1.0))
        # Cosine distance → similarity: similarity = 1 - distance
        similarity = round(1.0 - distance, 4)
        meta = match.get("metadata", {})
        passage_id = meta.get("passage_id", key.replace("content:", ""))

        # Skip the passage they just read
        if exclude_passage_id and passage_id == exclude_passage_id:
            continue

        # Only within the zone of proximal development
        if MIN_SIMILARITY <= similarity <= MAX_SIMILARITY:
            results.append({
                "passage_id": passage_id,
                "title": meta.get("title", ""),
                "difficulty_band": meta.get("difficulty_band", ""),
                "similarity_score": similarity,
            })

    # Sort by descending similarity, return top 3
    results.sort(key=lambda x: x["similarity_score"], reverse=True)
    logger.info(f"Vector query returned {len(results)} recommendations (filtered from {len(matches)})")
    return results[:3]
