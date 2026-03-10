"""
Learner Profile Schema
----------------------
Defines the structure for learner profiles stored in DynamoDB, including
adaptive difficulty tracking and cognitive error profiles.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
import json


@dataclass
class ErrorCategory:
    """
    One cognitive error dimension. Severity updated via EMA after each session.
    EMA formula: new = alpha * session_score + (1 - alpha) * old_severity
    alpha = 0.3 (recent sessions weighted more, history preserved)
    """
    severity: float                  # 1.0 (mild) to 10.0 (severe)
    patterns: List[str]              # e.g. ["bl_cluster", "tion_suffix"]
    confidence: float                # 0-1, how confident the model is
    session_count: int = 1           # how many sessions this is based on


@dataclass
class SessionSummary:
    """Compact record of one session stored inside the profile for quick access."""
    session_id: str
    date: str                        # YYYY-MM-DD
    words_per_minute: float
    accuracy_rate: float
    hesitation_count: int
    difficulty_band: str


@dataclass
class LearnerProfile:
    """
    Full learner profile. Written to DynamoDB after every session.

    Fields marked # Phase 1 are set immediately.
    Fields marked # Phase 2 are set after Nova 2 Lite reasoning runs.
    Fields marked # Phase 3 are set after Nova Embeddings runs.
    """

    # Identity - Phase 1
    learner_id: str
    created_at: str
    last_updated: str
    session_count: int

    # Difficulty tracking - Phase 1
    current_difficulty_band: str     # "grade_1", "grade_2", "grade_3"
    target_difficulty_band: str

    # Confidence proxy 1-10, starts at 5 - Phase 1
    overall_confidence_score: float

    # Recent session history (last 10) - Phase 1
    recent_sessions: List[SessionSummary] = field(default_factory=list)

    # Cognitive error categories - set to None until Phase 2
    phonological_decoding: Optional[ErrorCategory] = None
    visual_tracking: Optional[ErrorCategory] = None
    working_memory: Optional[ErrorCategory] = None
    fluency: Optional[ErrorCategory] = None

    # Embedding reference - set in Phase 3
    embedding_vector_key: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def get_top_error_category(self) -> Optional[str]:
        """Return name of most severe error category (for micro-drill targeting)."""
        categories = {
            "phonological_decoding": self.phonological_decoding,
            "visual_tracking": self.visual_tracking,
            "working_memory": self.working_memory,
            "fluency": self.fluency,
        }
        active = {k: v for k, v in categories.items() if v is not None}
        if not active:
            return None
        return max(active, key=lambda k: active[k].severity)

    def should_increase_difficulty(self) -> bool:
        """Last 3 sessions: WPM up >10% AND accuracy up >5%."""
        if len(self.recent_sessions) < 3:
            return False
        last3 = self.recent_sessions[-3:]
        wpm_trend = last3[-1].words_per_minute - last3[0].words_per_minute
        acc_trend = last3[-1].accuracy_rate - last3[0].accuracy_rate
        return wpm_trend > (last3[0].words_per_minute * 0.10) and acc_trend > 0.05

    def should_decrease_difficulty(self) -> bool:
        """Last 3 sessions: accuracy dropped >10%."""
        if len(self.recent_sessions) < 3:
            return False
        last3 = self.recent_sessions[-3:]
        acc_trend = last3[-1].accuracy_rate - last3[0].accuracy_rate
        return acc_trend < -0.10