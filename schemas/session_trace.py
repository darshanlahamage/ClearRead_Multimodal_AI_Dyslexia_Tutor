from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class WordEvent:
    """Represents a single word recognized during a reading session."""
    word: str
    position_index: int
    start_time_ms: int
    end_time_ms: int
    confidence: float
    flags: List[str] = field(default_factory=list)


@dataclass
class HesitationEvent:
    """Represents a significant pause detected before or during a word."""
    after_word_index: int
    pause_duration_ms: int
    preceding_word: str
    type: str   # "pre_word_pause" | "within_word_pause"


@dataclass
class RepetitionEvent:
    """Represents a word repeated by the learner during reading."""
    word: str
    first_position: int
    repeated_position: int
    type: str   # "immediate_repetition" | "near_repetition"


@dataclass
class AggregateMetrics:
    """Session-level reading metrics computed from word events."""
    words_per_minute: float
    accuracy_rate: float
    hesitation_count: int
    repetition_count: int
    mean_word_confidence: float
    low_confidence_words: List[str]
    flagged_phoneme_patterns: List[str]


@dataclass
class ReadingSessionTrace:
    """The complete trace of a reading session, including all events and metrics."""
    session_id: str
    learner_id: str
    timestamp_utc: str
    passage_id: str
    passage_difficulty_band: str
    duration_seconds: float
    word_events: List[WordEvent]
    hesitation_events: List[HesitationEvent]
    repetition_events: List[RepetitionEvent]
    aggregate_metrics: AggregateMetrics

    def to_dict(self) -> dict:
        """Convert the trace and its sub-objects to a dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize the trace to a JSON string."""
        return json.dumps(self.to_dict(), indent=2)