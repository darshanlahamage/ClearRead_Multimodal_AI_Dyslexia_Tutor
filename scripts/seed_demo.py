import json
import sys
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from config.settings import AWS_REGION, DYNAMO_PROFILES_TABLE, DYNAMO_SESSIONS_TABLE

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_profiles_table = _dynamodb.Table(DYNAMO_PROFILES_TABLE)
_sessions_table = _dynamodb.Table(DYNAMO_SESSIONS_TABLE)

LEARNER_ID = "demo_learner_001"

# 5 sessions showing clear improvement over 14 days
DEMO_SESSIONS = [
    {"days_ago": 14, "wpm": 42.0, "accuracy": 0.71, "hesitations": 11, "pattern": "bl_cluster"},
    {"days_ago": 11,  "wpm": 48.0, "accuracy": 0.74, "hesitations": 9,  "pattern": "bl_cluster"},
    {"days_ago": 8,  "wpm": 55.0, "accuracy": 0.79, "hesitations": 7,  "pattern": "bl_cluster"},
    {"days_ago": 5,  "wpm": 61.0, "accuracy": 0.83, "hesitations": 5,  "pattern": "bl_cluster"},
    {"days_ago": 2,  "wpm": 67.0, "accuracy": 0.87, "hesitations": 3,  "pattern": "bl_cluster"},
]


def _floats_to_decimal(obj):
    if isinstance(obj, float):
        return Decimal(str(round(obj, 6)))
    elif isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_floats_to_decimal(i) for i in obj]
    return obj


def create_session_item(session_data: dict, index: int) -> dict:
    """Build a minimal session-traces DynamoDB item."""
    session_id = str(uuid.uuid4())
    days_ago = session_data["days_ago"]
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    date_str = ts[:10]

    wpm = session_data["wpm"]
    accuracy = session_data["accuracy"]
    hesitations = session_data["hesitations"]
    total_words = int(wpm * 1.14)  # ~68 seconds per session
    duration = total_words / (wpm / 60)

    item = {
        "learner_id": LEARNER_ID,
        "session_id": session_id,
        "timestamp_utc": ts,
        "session_date": date_str,
        "passage_id": "g2_p001",
        "passage_difficulty_band": "grade_2",
        "duration_seconds": round(duration, 1),
        "word_events": [],   # minimal — not needed for dashboard
        "hesitation_events": [],
        "repetition_events": [],
        "aggregate_metrics": {
            "words_per_minute": wpm,
            "accuracy_rate": accuracy,
            "hesitation_count": hesitations,
            "repetition_count": 1,
            "mean_word_confidence": round(0.65 + index * 0.04, 3),
            "low_confidence_words": ["umbrella", "blue", "completely"],
            "flagged_phoneme_patterns": ["phoneme_bl_cluster", "phoneme_th_digraph"],
        },
    }
    return _floats_to_decimal(item)


def create_profile(recent_sessions: list) -> dict:
    """Build the demo learner profile."""
    now = datetime.now(timezone.utc).isoformat()
    created = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()

    profile = {
        "learner_id": LEARNER_ID,
        "created_at": created,
        "last_updated": now,
        "session_count": len(DEMO_SESSIONS),
        "current_difficulty_band": "grade_2",
        "target_difficulty_band": "grade_3",
        "overall_confidence_score": Decimal("6.2"),
        "recent_sessions": _floats_to_decimal(recent_sessions),
        "phonological_decoding": _floats_to_decimal({
            "severity": 7.2,
            "patterns": ["bl_cluster", "str_cluster"],
            "confidence": 0.88,
            "session_count": 5,
        }),
        "visual_tracking": _floats_to_decimal({
            "severity": 2.1,
            "patterns": [],
            "confidence": 0.71,
            "session_count": 5,
        }),
        "working_memory": _floats_to_decimal({
            "severity": 3.0,
            "patterns": ["long_sentence_loss"],
            "confidence": 0.78,
            "session_count": 5,
        }),
        "fluency": _floats_to_decimal({
            "severity": 4.8,
            "patterns": [],
            "confidence": 0.93,
            "session_count": 5,
        }),
    }
    return profile


def main():
    print(f"\n🌱 Seeding demo data for learner: {LEARNER_ID}")
    print("=" * 60)

    recent_sessions = []
    session_ids_created = []

    for i, sess_data in enumerate(DEMO_SESSIONS):
        item = create_session_item(sess_data, i)
        session_id = item["session_id"]
        days_ago = sess_data["days_ago"]
        date_str = item["session_date"]

        try:
            _sessions_table.put_item(Item=item)
            print(f"  ✅ Session {i+1}/5: {date_str} — WPM:{sess_data['wpm']:.0f}, "
                  f"Acc:{sess_data['accuracy']*100:.0f}%, Hes:{sess_data['hesitations']}")
            session_ids_created.append(session_id)

            # Build compact recent_session summary for profile
            recent_sessions.append(_floats_to_decimal({
                "session_id": session_id,
                "date": date_str,
                "words_per_minute": sess_data["wpm"],
                "accuracy_rate": sess_data["accuracy"],
                "hesitation_count": sess_data["hesitations"],
                "difficulty_band": "grade_2",
            }))
        except Exception as e:
            print(f"  Failed session {i+1}: {e}")

    # Create or overwrite the learner profile
    profile = create_profile(recent_sessions)
    try:
        _profiles_table.put_item(Item=profile)
        print(f"\n  Learner profile created/updated for {LEARNER_ID}")
    except Exception as e:
        print(f"\n  Failed to write profile: {e}")

    print("=" * 60)
    print(f" Demo seeding complete.")
    print(f"   Learner: {LEARNER_ID}")
    print(f"   Sessions seeded: {len(session_ids_created)}/5")
    print(f"   Progress arc: 42 → 67 WPM over 14 days")
    print(f"\n   Run the server and open http://localhost:8000 to see the progress chart.\n")


if __name__ == "__main__":
    main()
