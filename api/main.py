"""
FastAPI Main — Dyslexia Adaptive Learning Engine
-----------------------------------------------
Core API server handling HTTP routes, session persistence, and WebSocket 
orchestration for real-time speech coaching.
"""

import json
import logging
import sys
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add project root to path so relative imports work from api/
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.dynamo import (
    get_learner_profile,
    create_learner_profile,
    save_session_trace,
    update_profile_after_session,
    get_session_traces,
)
from core.trace_builder import build_trace
from schemas.session_trace import WordEvent
from api.websocket_handler import handle_websocket

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI Application

app = FastAPI(
    title="Dyslexia Adaptive Learning Engine",
    version="1.0.0",
    description="Real-time speech coaching using Amazon Nova models"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data Helpers

PASSAGES_DIR = Path(__file__).parent.parent / "data" / "passages"
SAMPLE_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sample_sessions"


def load_all_passages() -> list:
    """Scan data/passages/ recursively and return all passage dicts."""
    passages = []
    for f in sorted(PASSAGES_DIR.rglob("*.json")):
        try:
            data = json.loads(f.read_text())
            if "passage_id" in data:
                passages.append(data)
        except Exception:
            pass
    return passages


def get_passage_by_id(passage_id: str) -> Optional[dict]:
    for p in load_all_passages():
        if p["passage_id"] == passage_id:
            return p
    return None


# Schemas

class CreateLearnerRequest(BaseModel):
    learner_id: str
    difficulty_band: str = "grade_1"


class WordEventPayload(BaseModel):
    word: str
    position_index: int
    start_time_ms: int
    end_time_ms: int
    confidence: float
    flags: list = []


class SessionCompleteRequest(BaseModel):
    learner_id: str
    passage_id: str
    word_events: list[WordEventPayload]
    duration_seconds: float


class OfflineTestRequest(BaseModel):
    learner_id: str = "demo_learner_001"


# API Routes

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/passages")
def list_passages():
    """Return all available reading passages."""
    return load_all_passages()


@app.get("/api/learner/{learner_id}")
def get_learner(learner_id: str):
    """Fetch a learner profile by ID."""
    profile = get_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")
    return profile


@app.post("/api/learner")
def create_learner(req: CreateLearnerRequest):
    """Create a new learner profile."""
    existing = get_learner_profile(req.learner_id)
    if existing:
        return existing
    ok = create_learner_profile(req.learner_id, req.difficulty_band)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to create learner profile")
    return get_learner_profile(req.learner_id)


@app.get("/api/learner/{learner_id}/progress")
def get_progress(learner_id: str):
    """Return progress data formatted for charts."""
    profile = get_learner_profile(learner_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Learner '{learner_id}' not found")

    sessions = get_session_traces(learner_id, limit=10)

    wpm_trend = [
        {"date": s.get("session_date", ""), "value": float(s.get("aggregate_metrics", {}).get("words_per_minute", 0))}
        for s in sessions
    ]
    accuracy_trend = [
        {"date": s.get("session_date", ""), "value": round(float(s.get("aggregate_metrics", {}).get("accuracy_rate", 0)) * 100, 1)}
        for s in sessions
    ]

    # Error category trends from profile
    error_trends = {}
    for cat in ["phonological_decoding", "visual_tracking", "working_memory", "fluency"]:
        cat_data = profile.get(cat)
        if cat_data:
            error_trends[cat] = {
                "severity": float(cat_data.get("severity", 5.0)),
                "patterns": cat_data.get("patterns", []),
                "confidence": float(cat_data.get("confidence", 0.5)),
            }

    recent_sessions = profile.get("recent_sessions", [])

    return {
        "learner_id": learner_id,
        "session_count": profile.get("session_count", 0),
        "current_difficulty_band": profile.get("current_difficulty_band", "grade_1"),
        "overall_confidence_score": float(profile.get("overall_confidence_score", 5.0)),
        "wpm_trend": list(reversed(wpm_trend)),
        "accuracy_trend": list(reversed(accuracy_trend)),
        "error_trends": error_trends,
        "recent_sessions": [dict(s) for s in recent_sessions],
    }


@app.post("/api/session/offline-test")
def offline_test(req: OfflineTestRequest):
    """
    Dev/demo route: run the full pipeline using sample_trace_001.json.
    No microphone needed.
    """
    sample_path = SAMPLE_SESSIONS_DIR / "sample_trace_001.json"
    if not sample_path.exists():
        raise HTTPException(status_code=500, detail="sample_trace_001.json not found")

    sample = json.loads(sample_path.read_text())

    word_events = [
        WordEvent(
            word=w["word"],
            position_index=w["position_index"],
            start_time_ms=w["start_time_ms"],
            end_time_ms=w["end_time_ms"],
            confidence=w["confidence"],
            flags=w.get("flags", []),
        )
        for w in sample["word_events"]
    ]

    learner_id = req.learner_id
    profile = get_learner_profile(learner_id)
    if not profile:
        create_learner_profile(learner_id, difficulty_band="grade_2")
        profile = get_learner_profile(learner_id)

    trace = build_trace(
        learner_id=learner_id,
        passage_id=sample["passage_id"],
        passage_difficulty_band=sample["passage_difficulty_band"],
        raw_word_events=word_events,
        duration_seconds=sample["duration_seconds"],
    )

    save_session_trace(trace)
    update_profile_after_session(
        learner_id=learner_id,
        session_id=trace.session_id,
        session_date=trace.timestamp_utc[:10],
        words_per_minute=trace.aggregate_metrics.words_per_minute,
        accuracy_rate=trace.aggregate_metrics.accuracy_rate,
        hesitation_count=trace.aggregate_metrics.hesitation_count,
        difficulty_band=trace.passage_difficulty_band,
    )

    passage = get_passage_by_id(sample["passage_id"]) or {}
    updated_profile = get_learner_profile(learner_id) or {}
    response = _build_session_response(trace, passage, updated_profile)

    # Phase 3: Nova Lite analysis
    try:
        from core.lite_reasoner import analyze_session
        from core.text_adapter import generate_adapted_text, generate_micro_drills
        from storage.dynamo import update_error_profile

        error_profile = analyze_session(trace, updated_profile)
        update_error_profile(learner_id, error_profile)
        updated_profile = get_learner_profile(learner_id) or {}

        adapted = generate_adapted_text(passage, updated_profile)
        drills = generate_micro_drills(updated_profile)
        response["adapted_text"] = adapted
        response["micro_drills"] = drills
        response["error_profile"] = error_profile
    except Exception as e:
        logger.warning(f"Phase 3 skipped in offline-test: {e}")

    # Phase 4: Embeddings + Vector search
    try:
        from core.embedder import embed_text, profile_to_text
        from storage.vectors import upsert_learner_vector, query_content_recommendations

        profile_text = profile_to_text(updated_profile)
        learner_vector = embed_text(profile_text)
        metadata = {
            "learner_id": learner_id,
            "difficulty_band": updated_profile.get("current_difficulty_band", "grade_2"),
            "last_updated": trace.timestamp_utc,
        }
        upsert_learner_vector(learner_id, learner_vector, metadata)
        recommendations = query_content_recommendations(learner_vector, sample["passage_id"])
        response["recommendations"] = recommendations
    except Exception as e:
        logger.warning(f"Phase 4 skipped in offline-test: {e}")

    return response



@app.post("/api/session/complete")
async def session_complete(req: SessionCompleteRequest):
    """
    Save a completed live session trace and run full analysis pipeline.
    Called by browser after WebSocket session_complete event.
    """
    word_events = [
        WordEvent(
            word=w.word,
            position_index=w.position_index,
            start_time_ms=w.start_time_ms,
            end_time_ms=w.end_time_ms,
            confidence=w.confidence,
            flags=w.flags,
        )
        for w in req.word_events
    ]

    profile = get_learner_profile(req.learner_id)
    if not profile:
        create_learner_profile(req.learner_id, difficulty_band="grade_2")
        profile = get_learner_profile(req.learner_id)

    trace = build_trace(
        learner_id=req.learner_id,
        passage_id=req.passage_id,
        passage_difficulty_band=(profile or {}).get("current_difficulty_band", "grade_2"),
        raw_word_events=word_events,
        duration_seconds=req.duration_seconds,
    )

    save_session_trace(trace)
    update_profile_after_session(
        learner_id=req.learner_id,
        session_id=trace.session_id,
        session_date=trace.timestamp_utc[:10],
        words_per_minute=trace.aggregate_metrics.words_per_minute,
        accuracy_rate=trace.aggregate_metrics.accuracy_rate,
        hesitation_count=trace.aggregate_metrics.hesitation_count,
        difficulty_band=trace.passage_difficulty_band,
    )

    # Phase 3: Nova Lite analysis
    try:
        from core.lite_reasoner import analyze_session
        from core.text_adapter import generate_adapted_text, generate_micro_drills
        from storage.dynamo import update_error_profile

        updated_profile = get_learner_profile(req.learner_id) or {}
        error_profile = await asyncio.to_thread(analyze_session, trace, updated_profile)
        update_error_profile(req.learner_id, error_profile)
        updated_profile = get_learner_profile(req.learner_id) or {}

        passage = get_passage_by_id(req.passage_id) or {}
        adapted = await asyncio.to_thread(generate_adapted_text, passage, updated_profile)
        drills = await asyncio.to_thread(generate_micro_drills, updated_profile)
    except Exception as e:
        logger.warning(f"Phase 3 (Lite) skipped: {e}")
        updated_profile = profile or {}
        error_profile = {}
        passage = get_passage_by_id(req.passage_id) or {}
        adapted = None
        drills = []

    # Phase 4: Embeddings + Vectors
    recommendations = []
    try:
        import asyncio as _asyncio
        from core.embedder import embed_text, profile_to_text
        from storage.vectors import upsert_learner_vector, query_content_recommendations

        profile_text = profile_to_text(updated_profile)
        learner_vector = await _asyncio.to_thread(embed_text, profile_text)
        metadata = {
            "learner_id": req.learner_id,
            "difficulty_band": updated_profile.get("current_difficulty_band", "grade_2"),
            "last_updated": trace.timestamp_utc,
        }
        await _asyncio.to_thread(upsert_learner_vector, req.learner_id, learner_vector, metadata)
        recommendations = await _asyncio.to_thread(
            query_content_recommendations, learner_vector, req.passage_id
        )
    except Exception as e:
        logger.warning(f"Phase 4 (Embeddings) skipped: {e}")

    response = _build_session_response(trace, passage, updated_profile)
    if adapted:
        response["adapted_text"] = adapted
    if drills:
        response["micro_drills"] = drills
    if error_profile:
        response["error_profile"] = error_profile
    if recommendations:
        response["recommendations"] = recommendations

    return response


# WebSocket Endpoints

@app.websocket("/ws/session/{learner_id}")
async def websocket_session(ws: WebSocket, learner_id: str):
    await handle_websocket(ws, learner_id)


@app.websocket("/ws/interactive/{learner_id}")
async def websocket_interactive(ws: WebSocket, learner_id: str):
    from api.websocket_handler import handle_interactive_websocket
    await handle_interactive_websocket(ws, learner_id)


@app.websocket("/ws/webreader/{learner_id}")
async def websocket_webreader(ws: WebSocket, learner_id: str):
    from api.websocket_handler import handle_webreader_websocket
    await handle_webreader_websocket(ws, learner_id)


# Picture Reading (Nova 2 Lite Vision)

class VisionRequest(BaseModel):
    learner_id: str
    image_base64: str
    media_type: str = "image/jpeg"


@app.post("/api/vision/analyze")
async def vision_analyze(req: VisionRequest):
    """Analyze an image with Nova Vision and generate a reading passage."""
    import base64
    from core.vision_reader import analyze_image

    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception:
        return {"error": "Invalid base64 image data"}

    profile = {}
    try:
        p = get_learner_profile(req.learner_id)
        if p:
            profile = p.get("error_profile", p)
    except Exception:
        pass

    result = analyze_image(image_bytes, learner_profile=profile, media_type=req.media_type)
    return result


# Web Reader (URL Simplification + Sonic Discussion)

class WebSimplifyRequest(BaseModel):
    url: str
    learner_id: str = "guest"


@app.post("/api/web/simplify")
async def web_simplify(req: WebSimplifyRequest):
    """Fetch a URL, extract content, and simplify it for dyslexic readers."""
    import asyncio as _asyncio
    from core.web_reader import fetch_and_extract, simplify_for_dyslexia

    # Fetch and extract in a thread (blocking I/O)
    extracted = await _asyncio.to_thread(fetch_and_extract, req.url)
    if "error" in extracted:
        return extracted

    # Get learner profile for personalized simplification
    profile = {}
    try:
        p = get_learner_profile(req.learner_id)
        if p:
            profile = p
    except Exception:
        pass

    # Simplify with Nova Lite
    result = await _asyncio.to_thread(simplify_for_dyslexia, extracted, profile)
    return result


# Helpers


def _build_session_response(trace, passage: dict, profile: dict) -> dict:
    """Build the baseline session response (without Nova Lite / embeddings)."""
    m = trace.aggregate_metrics
    return {
        "session_id": trace.session_id,
        "session_summary": {
            "words_per_minute": m.words_per_minute,
            "accuracy_rate": m.accuracy_rate,
            "hesitation_count": m.hesitation_count,
            "repetition_count": m.repetition_count,
            "low_confidence_words": m.low_confidence_words[:5],
            "flagged_phoneme_patterns": m.flagged_phoneme_patterns[:3],
            "primary_pattern": m.flagged_phoneme_patterns[0] if m.flagged_phoneme_patterns else None,
        },
        "passage": {
            "passage_id": passage.get("passage_id", trace.passage_id),
            "title": passage.get("title", ""),
            "text": passage.get("text", ""),
            "difficulty_band": passage.get("difficulty_band", trace.passage_difficulty_band),
        },
        "adapted_text": None,
        "micro_drills": [],
        "error_profile": {},
        "recommendations": [],
        "progress_update": {
            "sessions_completed": profile.get("session_count", 0),
            "current_difficulty_band": profile.get("current_difficulty_band", "grade_1"),
        },
    }


# Frontend Service

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
