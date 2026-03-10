"""
Hesitation Detector
-------------------
Takes raw word events from Nova Sonic
and detects dyslexia-relevant signals:
  - Inter-word pauses (hesitations)
  - Word repetitions
  - Low-confidence words
  - Phoneme pattern flags
"""

from typing import List, Tuple
from schemas.session_trace import WordEvent, HesitationEvent, RepetitionEvent
from config.settings import (
    HESITATION_PAUSE_MS,
    CONFIDENCE_THRESHOLD,
    REPETITION_WINDOW,
    PHONEME_PATTERNS,
)


def flag_phoneme_patterns(word: str) -> List[str]:
    """
    Check if a word contains any known hard phoneme patterns.
    Returns list of flag strings like ["phoneme_cluster_bl", "tion_suffix"].
    """
    word_lower = word.lower().strip(".,!?;:'\"")
    flags = []
    for pattern_name, substrings in PHONEME_PATTERNS.items():
        for sub in substrings:
            if sub in word_lower:
                flags.append(f"phoneme_{pattern_name}")
                break
    return flags


def detect_hesitations(word_events: List[WordEvent]) -> List[HesitationEvent]:
    """
    Compare end_time of word[n] to start_time of word[n+1].
    Gap > HESITATION_PAUSE_MS is flagged as a hesitation.
    """
    hesitations = []
    for i in range(len(word_events) - 1):
        current = word_events[i]
        next_word = word_events[i + 1]
        gap_ms = next_word.start_time_ms - current.end_time_ms
        if gap_ms > HESITATION_PAUSE_MS:
            hesitations.append(HesitationEvent(
                after_word_index=i,
                pause_duration_ms=gap_ms,
                preceding_word=current.word,
                type="pre_word_pause"
            ))
    return hesitations


def detect_repetitions(word_events: List[WordEvent]) -> List[RepetitionEvent]:
    """
    Check for the same word appearing within a REPETITION_WINDOW-word window.
    Catches: "the the cat" (immediate) and "the cat the" (near).
    """
    repetitions = []
    words = [e.word.lower().strip(".,!?;:'\"") for e in word_events]

    for i, word in enumerate(words):
        # Look forward within the window
        window_end = min(i + REPETITION_WINDOW + 1, len(words))
        for j in range(i + 1, window_end):
            if words[j] == word and len(word) > 2:  # skip tiny words like "a"
                rep_type = "immediate_repetition" if j == i + 1 else "near_repetition"
                # Avoid double-logging same repetition pair
                already_logged = any(
                    r.first_position == i and r.repeated_position == j
                    for r in repetitions
                )
                if not already_logged:
                    repetitions.append(RepetitionEvent(
                        word=word_events[i].word,
                        first_position=i,
                        repeated_position=j,
                        type=rep_type
                    ))
    return repetitions


def annotate_confidence_flags(word_events: List[WordEvent]) -> List[WordEvent]:
    """
    Add 'uncertain_word' flag to any word below the confidence threshold.
    Modifies word_events in place and returns them.
    """
    for event in word_events:
        if event.confidence < CONFIDENCE_THRESHOLD:
            if "uncertain_word" not in event.flags:
                event.flags.append("uncertain_word")
    return word_events


def run_all_detections(
    word_events: List[WordEvent],
) -> Tuple[List[WordEvent], List[HesitationEvent], List[RepetitionEvent]]:
    """
    Main entry point. Run all detections on a list of WordEvents.

    Returns:
        annotated_words  - WordEvents with phoneme + confidence flags added
        hesitations      - list of HesitationEvents
        repetitions      - list of RepetitionEvents
    """
    # 1. Add phoneme pattern flags to each word
    for event in word_events:
        phoneme_flags = flag_phoneme_patterns(event.word)
        event.flags.extend(phoneme_flags)

    # 2. Add confidence flags
    word_events = annotate_confidence_flags(word_events)

    # 3. Detect hesitations from timing gaps
    hesitations = detect_hesitations(word_events)

    # 4. Mark hesitation-adjacent words
    hesitation_word_indices = {h.after_word_index for h in hesitations}
    for i, event in enumerate(word_events):
        if i in hesitation_word_indices and "hesitation_after" not in event.flags:
            event.flags.append("hesitation_after")

    # 5. Detect repetitions
    repetitions = detect_repetitions(word_events)

    # 6. Mark repeated words
    repeated_indices = set()
    for r in repetitions:
        repeated_indices.add(r.first_position)
        repeated_indices.add(r.repeated_position)
    for i, event in enumerate(word_events):
        if i in repeated_indices and "repetition" not in event.flags:
            event.flags.append("repetition")

    return word_events, hesitations, repetitions


def get_low_confidence_words(word_events: List[WordEvent]) -> List[str]:
    return [e.word for e in word_events if "uncertain_word" in e.flags]


def get_flagged_phoneme_patterns(word_events: List[WordEvent]) -> List[str]:
    """
    Returns a unique list of phoneme pattern flags observed across all word events,
    sorted by their frequency of occurrence (most frequent first).
    """
    pattern_counts = {}
    for event in word_events:
        for flag in event.flags:
            if flag.startswith("phoneme_"):
                pattern_counts[flag] = pattern_counts.get(flag, 0) + 1
    return sorted(pattern_counts, key=pattern_counts.get, reverse=True)