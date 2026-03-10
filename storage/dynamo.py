"""
DynamoDB Storage
----------------
Two tables:
    learner-profiles   PK: learner_id
    session-traces     PK: learner_id, SK: session_id
"""

import boto3
import json
from datetime import datetime, timezone
from decimal import Decimal

from schemas.session_trace import ReadingSessionTrace
from schemas.learner_profile import LearnerProfile
from config.settings import AWS_REGION, DYNAMO_PROFILES_TABLE, DYNAMO_SESSIONS_TABLE


# DynamoDB resource (higher-level, simpler API than client)
_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_profiles_table = _dynamodb.Table(DYNAMO_PROFILES_TABLE)
_sessions_table = _dynamodb.Table(DYNAMO_SESSIONS_TABLE)


def _floats_to_decimal(obj):
    """
    DynamoDB doesn't accept Python float — convert to Decimal.
    Recursively handles dicts and lists.
    """
    if isinstance(obj, float):
        return Decimal(str(round(obj, 6)))
    elif isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


def _decimal_to_float(obj):
    """Convert Decimal back to float when reading from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


# ── Session Traces ────────────────────────────────────────────────────────────

def save_session_trace(trace: ReadingSessionTrace) -> bool:
    """
    Write a ReadingSessionTrace to the session-traces DynamoDB table.
    Returns True on success.
    """
    try:
        item = _floats_to_decimal(trace.to_dict())
        # Add session_date for easy querying
        item["session_date"] = trace.timestamp_utc[:10]
        _sessions_table.put_item(Item=item)
        logger.info(f"Session trace saved: {trace.session_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to save session trace: {e}")
        return False


def get_session_traces(learner_id: str, limit: int = 10) -> list:
    """
    Retrieve the N most recent session traces for a learner.
    """
    try:
        response = _sessions_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("learner_id").eq(learner_id),
            ScanIndexForward=False,   # newest first
            Limit=limit
        )
        return [_decimal_to_float(item) for item in response.get("Items", [])]
    except Exception as e:
        logger.error(f"Failed to get session traces: {e}")
        return []


# ── Learner Profiles ──────────────────────────────────────────────────────────

def get_learner_profile(learner_id: str) -> dict | None:
    """
    Fetch a learner profile from DynamoDB.
    Returns None if this is the learner's first session.
    """
    try:
        response = _profiles_table.get_item(Key={"learner_id": learner_id})
        item = response.get("Item")
        if item:
            return _decimal_to_float(item)
        return None
    except Exception as e:
        logger.error(f"Failed to get learner profile: {e}")
        return None


def create_learner_profile(learner_id: str, difficulty_band: str = "grade_1") -> bool:
    """
    Create a new learner profile for a first-time learner.
    Called in main.py when get_learner_profile returns None.
    """
    now = datetime.now(timezone.utc).isoformat()
    profile = {
        "learner_id": learner_id,
        "created_at": now,
        "last_updated": now,
        "session_count": 0,
        "current_difficulty_band": difficulty_band,
        "overall_confidence_score": Decimal("5.0"),
        # Error categories populated after Phase 2 (Nova 2 Lite reasoning)
        "phonological_decoding": None,
        "visual_tracking": None,
        "working_memory": None,
        "fluency": None,
        "embedding_vector_key": None,
    }
    # Remove None values — DynamoDB doesn't accept None
    profile = {k: v for k, v in profile.items() if v is not None}
    try:
        _profiles_table.put_item(Item=profile)
        logger.info(f"New learner profile created: {learner_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to create learner profile: {e}")
        return False


def increment_session_count(learner_id: str) -> bool:
    """Increment session_count and update last_updated timestamp."""
    try:
        _profiles_table.update_item(
            Key={"learner_id": learner_id},
            UpdateExpression="SET session_count = session_count + :inc, last_updated = :ts",
            ExpressionAttributeValues={
                ":inc": 1,
                ":ts": datetime.now(timezone.utc).isoformat()
            }
        )
        return True
    except Exception as e:
        logger.error(f"Failed to increment session count: {e}")
        return False


def update_profile_after_session(
    learner_id: str,
    session_id: str,
    session_date: str,
    words_per_minute: float,
    accuracy_rate: float,
    hesitation_count: int,
    difficulty_band: str,
) -> bool:
    """
    Update learner profile after a session completes:
    - Appends a compact session summary to recent_sessions (keep last 10)
    - Increments session_count
    - Updates last_updated timestamp
    
    Called from main.py (CLI) and api/main.py after every session.
    """
    summary = _floats_to_decimal({
        "session_id": session_id,
        "date": session_date,
        "words_per_minute": words_per_minute,
        "accuracy_rate": accuracy_rate,
        "hesitation_count": hesitation_count,
        "difficulty_band": difficulty_band,
    })
    now = datetime.now(timezone.utc).isoformat()
    try:
        # Fetch current recent_sessions so we can cap at 10
        response = _profiles_table.get_item(Key={"learner_id": learner_id})
        item = response.get("Item", {})
        recent = list(item.get("recent_sessions", []))
        recent.append(summary)
        if len(recent) > 10:
            recent = recent[-10:]

        _profiles_table.update_item(
            Key={"learner_id": learner_id},
            UpdateExpression=(
                "SET session_count = if_not_exists(session_count, :zero) + :inc, "
                "last_updated = :ts, "
                "recent_sessions = :sessions"
            ),
            ExpressionAttributeValues={
                ":inc": 1,
                ":zero": 0,
                ":ts": now,
                ":sessions": recent,
            }
        )
        logger.info(f"Profile updated for {learner_id} (session {session_id[:8]})")
        return True
    except Exception as e:
        logger.error(f"Failed to update profile after session: {e}")
        return False


def update_error_profile(learner_id: str, error_profile: dict) -> bool:
    """
    Write the 4 cognitive error categories to the learner profile.
    Called after Nova 2 Lite analyzes a session.
    
    error_profile format:
        {
          "phonological_decoding": {"severity": 7.2, "patterns": [...], "confidence": 0.88, "session_count": 5},
          "visual_tracking":       {...},
          "working_memory":        {...},
          "fluency":               {...}
        }
    """
    try:
        profile_decimal = _floats_to_decimal(error_profile)
        now = datetime.now(timezone.utc).isoformat()
        coach_fb = profile_decimal.get("coach_feedback", profile_decimal.get("coach_message", "Great job today!"))

        _profiles_table.update_item(
            Key={"learner_id": learner_id},
            UpdateExpression=(
                "SET phonological_decoding = :pd, "
                "visual_tracking = :vt, "
                "working_memory = :wm, "
                "fluency = :fl, "
                "coach_feedback = :cf, "
                "last_updated = :ts"
            ),
            ExpressionAttributeValues={
                ":pd": profile_decimal.get("phonological_decoding", {}),
                ":vt": profile_decimal.get("visual_tracking", {}),
                ":wm": profile_decimal.get("working_memory", {}),
                ":fl": profile_decimal.get("fluency", {}),
                ":cf": coach_fb,
                ":ts": now,
            }
        )
        logger.info(f"Error profile updated for {learner_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to update error profile: {e}")
        return False