"""
Trace Builder
-------------
Orchestrates the creation of a full ReadingSessionTrace by combining 
WordEvents with diagnostic analysis from hesitation and repetition detectors.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from schemas.session_trace import (
    WordEvent, HesitationEvent, RepetitionEvent,
    AggregateMetrics, ReadingSessionTrace
)
from core.hesitation_detector import (
    run_all_detections,
    get_low_confidence_words,
    get_flagged_phoneme_patterns
)


def build_trace(
    learner_id: str,
    passage_id: str,
    passage_difficulty_band: str,
    raw_word_events: List[WordEvent],
    duration_seconds: float,
) -> ReadingSessionTrace:
    """
    Main entry point called after a Nova Sonic session ends.

    Args:
        learner_id              - who is reading
        passage_id              - which passage was read
        passage_difficulty_band - e.g. "grade_2"
        raw_word_events         - list of WordEvent from sonic_session.py
        duration_seconds        - total session duration

    Returns:
        A complete ReadingSessionTrace ready for DynamoDB storage.
    """

    # Run all detections
    annotated_words, hesitations, repetitions = run_all_detections(raw_word_events)

    # Compute aggregate metrics
    total_words = len(annotated_words)
    words_per_minute = (total_words / duration_seconds * 60) if duration_seconds > 0 else 0

    # Accuracy: words with no flags at all
    clean_words = [w for w in annotated_words if not w.flags]
    accuracy_rate = len(clean_words) / total_words if total_words > 0 else 1.0

    confidences = [w.confidence for w in annotated_words]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    low_conf_words = get_low_confidence_words(annotated_words)
    flagged_patterns = get_flagged_phoneme_patterns(annotated_words)

    metrics = AggregateMetrics(
        words_per_minute=round(words_per_minute, 1),
        accuracy_rate=round(accuracy_rate, 3),
        hesitation_count=len(hesitations),
        repetition_count=len(repetitions),
        mean_word_confidence=round(mean_confidence, 3),
        low_confidence_words=low_conf_words[:10],   # top 10
        flagged_phoneme_patterns=flagged_patterns[:5],  # top 5 patterns
    )

    trace = ReadingSessionTrace(
        session_id=str(uuid.uuid4()),
        learner_id=learner_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        passage_id=passage_id,
        passage_difficulty_band=passage_difficulty_band,
        duration_seconds=round(duration_seconds, 2),
        word_events=annotated_words,
        hesitation_events=hesitations,
        repetition_events=repetitions,
        aggregate_metrics=metrics,
    )

    return trace