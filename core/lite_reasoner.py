"""
Nova 2 Lite Reasoner
-------------------
Analyzes a ReadingSessionTrace using Nova 2 Lite with extended thinking
to produce a CognitiveErrorProfile with 4 severity dimensions.

Uses:
    boto3.client("bedrock-runtime").converse()
    Model: us.amazon.nova-2-lite-v1:0
    Extended thinking: budget_tokens=8000
"""

import json
import logging
import re
import boto3

from schemas.session_trace import ReadingSessionTrace
from config.settings import AWS_REGION, LITE_MODEL_ID

logger = logging.getLogger(__name__)

_bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)

# EMA alpha: recent session gets 30% weight, history gets 70%
EMA_ALPHA = 0.3


def build_session_prompt(trace: ReadingSessionTrace, profile: dict) -> str:
    """
    Convert a session trace into a compact diagnostic prompt for Nova 2 Lite.
    Keeps total under ~2000 tokens by summarizing rather than dumping raw JSON.
    """
    m = trace.aggregate_metrics

    # Find the 5 words with longest hesitation gaps (most diagnostic)
    hes_sorted = sorted(
        trace.hesitation_events, key=lambda h: h.pause_duration_ms, reverse=True
    )
    top_hesitations = [
        f"'{h.preceding_word}' (pause {h.pause_duration_ms}ms after)"
        for h in hes_sorted[:5]
    ]

    # Low-confidence words
    low_conf = [
        f"'{e.word}' (conf={e.confidence:.2f}, flags={e.flags})"
        for e in trace.word_events
        if e.confidence < 0.75
    ][:8]

    # Phoneme flags seen
    phoneme_flags = list(set(
        flag for e in trace.word_events for flag in e.flags if flag.startswith("phoneme_")
    ))

    # Repetitions
    reps = [
        f"'{r.word}' repeated (positions {r.first_position} and {r.repeated_position})"
        for r in trace.repetition_events[:5]
    ]

    # Prior profile context
    prior_context = ""
    for cat in ["phonological_decoding", "visual_tracking", "working_memory", "fluency"]:
        cat_data = profile.get(cat)
        if cat_data:
            sev = cat_data.get("severity", 5.0)
            pats = cat_data.get("patterns", [])
            prior_context += f"  - {cat}: severity={sev:.1f}, patterns={pats}\n"

    prompt = f"""You are a reading specialist diagnosing a dyslexic learner's cognitive error patterns.

SESSION METRICS:
- Words per minute: {m.words_per_minute}
- Accuracy rate: {m.accuracy_rate * 100:.0f}% (words with no flags)
- Hesitation count: {m.hesitation_count}
- Repetition count: {m.repetition_count}
- Mean word confidence: {m.mean_word_confidence:.2f}

TOP HESITATION MOMENTS (longest pauses in the reading):
{chr(10).join(top_hesitations) if top_hesitations else '  None detected'}

LOW-CONFIDENCE WORDS (Sonic uncertain about these):
{chr(10).join(low_conf) if low_conf else '  None'}

PHONEME PATTERNS TRIGGERED:
{', '.join(phoneme_flags) if phoneme_flags else 'None'}

WORD REPETITIONS:
{chr(10).join(reps) if reps else '  None'}

PRIOR SESSION PROFILE (if any):
{prior_context if prior_context else '  First session — no prior data'}

TASK: Score the reader's difficulties in 4 areas, then write a structured 'coach_feedback' object.

Each dimension must have:
- severity: float 1.0–10.0 (1=minimal, 10=severe)
- patterns: list of specific sub-patterns observed (use short strings)
- confidence: float 0–1

The 'coach_feedback' must be a JSON object with EXACTLY these 4 fields:
- "praise": One sentence about a SPECIFIC word they read correctly and what was good about it. (e.g. "You read the word 'butterfly' perfectly — great job with that tricky word!")
- "correction": One sentence identifying ONE specific word they struggled with, explaining the phonics rule and how to say it correctly. Include syllable breakdown. (e.g. "The word 'through' has a 'th' sound — put your tongue between your teeth and blow! Th-rough.")
- "tip": A practical phonics tip they can remember for next time. Make it catchy and memorable. (e.g. "Remember: when two letters make one sound, like 'sh' or 'th', they are best friends who always stick together!")
- "encouragement": A motivating sign-off that makes them want to practice more. (e.g. "You are getting so much better every time! I can't wait to read with you again!")

Each field should be 1-2 sentences, using simple language a child would understand.

Return ONLY a JSON object with EXACTLY this structure, no markdown fencing, no explanation:
{{
  "phonological_decoding": {{"severity": 7.2, "patterns": ["bl_cluster", "str_cluster"], "confidence": 0.88}},
  "visual_tracking":       {{"severity": 2.1, "patterns": [], "confidence": 0.71}},
  "working_memory":        {{"severity": 3.0, "patterns": ["long_sentence_loss"], "confidence": 0.78}},
  "fluency":               {{"severity": 4.8, "patterns": [], "confidence": 0.93}},
  "coach_feedback": {{
    "praise": "You read the word 'sunshine' perfectly — that is a big word and you nailed it!",
    "correction": "The word 'bright' starts with a 'br' blend. Try saying 'brr' then 'ight'. Br-ight!",
    "tip": "When you see 'br' or 'bl' at the start, say the first two sounds together really fast, like 'brr' or 'bll'!",
    "encouragement": "You are getting stronger every time you read! Keep it up, superstar!"
  }}
}}"""

    return prompt


def analyze_session(trace: ReadingSessionTrace, profile: dict) -> dict:
    """
    Call Nova 2 Lite with extended thinking to classify cognitive error patterns.
    Applies EMA to blend this session's score with the learner's history.
    
    Returns:
        Updated error profile dict with 4 categories, ready for update_error_profile()
    """
    prompt = build_session_prompt(trace, profile)
    logger.info(f"Calling Nova Lite (extended thinking) for session {trace.session_id[:8]}")

    try:
        response = _bedrock.converse(
            modelId=LITE_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            additionalModelRequestFields={
                "thinking": {"type": "enabled", "budget_tokens": 8000}
            },
        )
    except Exception as e:
        logger.error(f"Nova Lite converse failed: {e}")
        return _default_error_profile()

    # Parse response — skip "thinking" blocks, only parse "text" blocks
    session_scores = None
    content_blocks = response.get("output", {}).get("message", {}).get("content", [])
    for block in content_blocks:
        if block.get("type") == "thinking":
            continue
        if block.get("type") == "text":
            raw_text = block.get("text", "")
            # Strip any markdown code fences that might have snuck in
            cleaned = re.sub(r"```json|```", "", raw_text).strip()
            try:
                session_scores = json.loads(cleaned)
                break
            except json.JSONDecodeError:
                # Try to extract JSON object from within the text
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    try:
                        session_scores = json.loads(match.group())
                        break
                    except json.JSONDecodeError:
                        pass

    if not session_scores:
        logger.warning("Failed to parse Nova Lite response — using defaults")
        session_scores = _default_error_profile()

    # Apply EMA blending with prior profile
    updated_profile = {}
    for cat in ["phonological_decoding", "visual_tracking", "working_memory", "fluency"]:
        new_scores = session_scores.get(cat, {})
        new_sev = float(new_scores.get("severity", 5.0))
        new_pats = new_scores.get("patterns", [])
        new_conf = float(new_scores.get("confidence", 0.7))

        prior = profile.get(cat)
        if prior and isinstance(prior, dict):
            prior_sev = float(prior.get("severity", 5.0))
            prior_pats = prior.get("patterns", [])
            prior_count = int(prior.get("session_count", 1))
            # EMA blend
            blended_sev = EMA_ALPHA * new_sev + (1 - EMA_ALPHA) * prior_sev
            # Merge patterns (deduplicated)
            merged_pats = list(set(prior_pats + new_pats))
            session_count = prior_count + 1
        else:
            blended_sev = new_sev
            merged_pats = new_pats
            session_count = 1

        updated_profile[cat] = {
            "severity": round(blended_sev, 2),
            "patterns": merged_pats,
            "confidence": round(new_conf, 3),
            "session_count": session_count,
        }

    logger.info(f"Error profile computed: {updated_profile}")
    return updated_profile


def _default_error_profile() -> dict:
    """Fallback profile when Nova Lite call fails."""
    return {
        "phonological_decoding": {"severity": 5.0, "patterns": [], "confidence": 0.5, "session_count": 1},
        "visual_tracking":       {"severity": 3.0, "patterns": [], "confidence": 0.5, "session_count": 1},
        "working_memory":        {"severity": 4.0, "patterns": [], "confidence": 0.5, "session_count": 1},
        "fluency":               {"severity": 5.0, "patterns": [], "confidence": 0.5, "session_count": 1},
    }
