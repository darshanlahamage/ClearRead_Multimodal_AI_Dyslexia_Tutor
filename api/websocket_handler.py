"""
WebSocket Handler — Nova Sonic Bridge
---------------------------------------
Bridges the browser microphone to Nova Sonic's bidirectional Bedrock stream.

Protocol:
  Browser → Server (JSON):    {type: "start_audio"} | {type: "stop_audio"}
  Browser → Server (binary):  Raw PCM 16-bit 16kHz mono audio chunks
  Server → Browser (JSON):    {type: "word", word, confidence, position} | {type: "session_complete", ...} | {type: "status", message}
  Server → Browser (binary):  Raw PCM audio bytes from Nova Sonic (spoken correction)
"""

import asyncio
import base64
import json
import time
import logging
from fastapi import WebSocket, WebSocketDisconnect
from core.sonic_session import NovaSonicSession

logger = logging.getLogger(__name__)


async def handle_websocket(ws: WebSocket, learner_id: str):
    """
    Main WebSocket handler. Called by api/main.py for /ws/session/{learner_id}.

    Lifecycle:
        1. Wait for {type: "start_audio"} control message
        2. Initialize NovaSonicSession, send setup events
        3. Start response-processing task (receives words + audio from Sonic)
        4. Loop: receive binary PCM from browser → forward to Sonic
        5. On {type: "stop_audio"}: end Sonic stream, collect word_events
        6. Send {type: "session_complete"} to browser
        7. Clean disconnect
    """
    await ws.accept()
    logger.info(f"WebSocket connected: learner={learner_id}")

    session: NovaSonicSession = NovaSonicSession(learner_id=learner_id)
    response_task = None
    session_started = False
    session_start_wall = 0.0

    try:
        await ws.send_json({"type": "status", "message": "connected"})

        while True:
            try:
                # Receive next message (binary or text/JSON)
                message = await ws.receive()
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: learner={learner_id}")
                break

                        # Process binary PCM audio chunks from browser
            if message.get("bytes") is not None:
                if session_started:
                    pcm_chunk = message["bytes"]
                    await session._send_audio_chunk(pcm_chunk)
                continue

                        # Process JSON control messages
            raw_text = message.get("text", "")
            if not raw_text:
                continue

            try:
                ctrl = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            msg_type = ctrl.get("type", "")

            if msg_type == "start_audio":
                # Initialize Sonic and start streaming
                logger.info(f"start_audio: initializing Sonic for learner={learner_id}")
                try:
                    await session.start_streaming()
                    session_started = True
                    session_start_wall = time.monotonic()

                    # Start consuming Sonic's output in a background task
                    response_task = asyncio.create_task(
                        _stream_responses_to_browser(ws, session)
                    )
                    await ws.send_json({"type": "status", "message": "recording"})
                    logger.info("Sonic stream open, response task started")
                except Exception as e:
                    logger.error(f"Failed to start Sonic: {e}")
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg_type == "stop_audio":
                # Stop sending audio, let Sonic finalize
                logger.info(f"stop_audio received for learner={learner_id}")
                if not session_started:
                    continue

                duration = time.monotonic() - session_start_wall

                try:
                    await session.stop_streaming()
                except Exception as e:
                    logger.warning(f"Error stopping stream: {e}")

                # Wait for response task to wind down (with timeout)
                if response_task and not response_task.done():
                    try:
                        await asyncio.wait_for(
                            asyncio.shield(response_task), timeout=5.0
                        )
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        response_task.cancel()

                # Serialize word events for browser
                word_events_payload = [
                    {
                        "word": evt.word,
                        "position_index": evt.position_index,
                        "start_time_ms": evt.start_time_ms,
                        "end_time_ms": evt.end_time_ms,
                        "confidence": evt.confidence,
                        "flags": evt.flags,
                    }
                    for evt in session.word_events
                ]

                await ws.send_json({
                    "type": "session_complete",
                    "word_events": word_events_payload,
                    "duration_seconds": round(duration, 2),
                })
                logger.info(
                    f"session_complete sent: {len(word_events_payload)} words, {duration:.1f}s"
                )
                break  # Close WebSocket after session_complete

    except Exception as e:
        logger.error(f"WebSocket handler error: {e}")
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Always clean up Sonic session
        if session_started:
            try:
                session.is_active = False
                await session.stop_streaming()
            except Exception:
                pass
        if response_task and not response_task.done():
            response_task.cancel()
        logger.info(f"WebSocket handler exiting: learner={learner_id}")


async def _stream_responses_to_browser(ws: WebSocket, session: NovaSonicSession):
    """
    Background task: read Sonic's output events and forward to browser.
    
    - textOutput events → JSON {type: "word", word, confidence, position}
    - audioOutput events → binary raw PCM bytes (browser plays these)
    
    Runs until session.is_active becomes False or stream ends.
    """
    import json as _json

    try:
        while session.is_active:
            try:
                output = await session.stream.await_output()
                result = await output[1].receive()

                if not (result.value and result.value.bytes_):
                    continue

                raw = result.value.bytes_.decode("utf-8")
                data = _json.loads(raw)

                if "event" not in data:
                    continue

                event = data["event"]

                                # contentStart: initialize role and speculative tracking
                if "contentStart" in event:
                    content_start = event["contentStart"]
                    session._role = content_start.get("role", "")
                    additional = content_start.get("additionalModelFields", "")
                    if additional:
                        try:
                            af = _json.loads(additional)
                            session._capture_transcript = (
                                af.get("generationStage") == "SPECULATIVE"
                            )
                        except _json.JSONDecodeError:
                            session._capture_transcript = False

                                # textOutput: capture word-level transcript from Sonic
                elif "textOutput" in event:
                    text = event["textOutput"].get("content", "").strip()
                    role = event["textOutput"].get("role", session._role or "")
                    if text and (role == "USER" or session._capture_transcript):
                        words = text.split()
                        for word in words:
                            if not word:
                                continue
                            now_ms = int(
                                (time.monotonic() - session.session_start_time) * 1000
                            )
                            confidence = float(event["textOutput"].get("confidence", 0.85))
                            from schemas.session_trace import WordEvent
                            word_event = WordEvent(
                                word=word,
                                position_index=session.word_position,
                                start_time_ms=session.last_word_end_ms,
                                end_time_ms=now_ms,
                                confidence=confidence,
                                flags=[],
                            )
                            session.word_events.append(word_event)
                            session.last_word_end_ms = now_ms
                            session.word_position += 1

                            # Send word highlight to browser
                            try:
                                await ws.send_json({
                                    "type": "word",
                                    "word": word,
                                    "confidence": confidence,
                                    "position": word_event.position_index,
                                })
                            except Exception:
                                return  # Browser disconnected

                                # audioOutput: handle speech response from Sonic
                elif "audioOutput" in event:
                    b64_audio = event["audioOutput"].get("content", "")
                    if b64_audio:
                        # Muted: We no longer send real-time audio from Sonic back to the browser
                        # to prevent heavy lag and interruptions while the student is reading.
                        # Feedback is given at the end via TTS.
                        pass

                                # Handle stream termination events
                elif "completionEnd" in event or "sessionEnd" in event:
                    session.is_active = False
                    break

            except StopAsyncIteration:
                session.is_active = False
                break
            except Exception as e:
                logger.warning(f"Response stream error: {e}")
                continue

    except Exception as e:
        logger.error(f"Fatal response stream error: {e}")
        session.is_active = False


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive Practice Mode — Full Speech-to-Speech
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_interactive_websocket(ws: WebSocket, learner_id: str):
    """
    WebSocket handler for Interactive Practice mode.
    Unlike the assessment handler, this streams Sonic's audio BACK to the browser
    so the student can hear Coach Nova speaking.
    """
    await ws.accept()
    logger.info(f"Interactive WS connected: learner={learner_id}")

    from core.interactive_session import InteractiveSonicSession

    session: InteractiveSonicSession = None
    response_task = None
    session_started = False

    try:
        await ws.send_json({"type": "status", "message": "connected"})

        while True:
            try:
                message = await ws.receive()
            except WebSocketDisconnect:
                break

            # Binary: PCM audio
            if message.get("bytes") is not None:
                if session_started:
                    await session._send_audio_chunk(message["bytes"])
                continue

            # Text: JSON control
            raw_text = message.get("text", "")
            if not raw_text:
                continue

            try:
                ctrl = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            msg_type = ctrl.get("type", "")

            if msg_type == "start_audio":
                words_context = ctrl.get("words_context", "")
                
                # Fetch the learner's error profile for personalized practice
                error_profile = {}
                try:
                    from storage.dynamo import get_learner_profile
                    profile = get_learner_profile(learner_id)
                    if profile:
                        error_profile = profile.get("error_profile", {})
                        # Also grab recent low confidence words
                        recent = profile.get("recent_sessions", [])
                        if recent:
                            last = recent[-1] if isinstance(recent[-1], dict) else {}
                            low_conf = last.get("low_confidence_words", [])
                            if low_conf:
                                error_profile["low_confidence_words"] = low_conf
                except Exception as e:
                    logger.warning(f"Could not fetch profile for personalization: {e}")

                session = InteractiveSonicSession(
                    learner_id=learner_id,
                    words_context=words_context,
                    error_profile=error_profile
                )
                try:
                    await session.start_streaming()
                    session_started = True
                    response_task = asyncio.create_task(
                        _stream_interactive_responses(ws, session)
                    )
                    await ws.send_json({"type": "status", "message": "listening"})
                except Exception as e:
                    logger.error(f"Failed to start interactive Sonic: {e}")
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg_type == "stop_audio":
                if not session_started:
                    continue
                try:
                    await session.stop_streaming()
                except Exception:
                    pass
                if response_task and not response_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(response_task), timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        response_task.cancel()
                break

    except Exception as e:
        logger.error(f"Interactive WS error: {e}")
    finally:
        if session_started and session:
            try:
                session.is_active = False
                await session.stop_streaming()
            except Exception:
                pass
        if response_task and not response_task.done():
            response_task.cancel()
        logger.info(f"Interactive WS exiting: learner={learner_id}")


async def _stream_interactive_responses(ws: WebSocket, session):
    """
    Read Sonic output and forward BOTH text AND audio to the browser.
    Text → JSON {type:"transcript", role, text}
    Audio → binary PCM bytes
    """
    import json as _json

    try:
        while session.is_active:
            try:
                output = await session.stream.await_output()
                result = await output[1].receive()

                if not (result.value and result.value.bytes_):
                    continue

                raw = result.value.bytes_.decode("utf-8")
                data = _json.loads(raw)

                if "event" not in data:
                    continue

                event = data["event"]

                if "contentStart" in event:
                    cs = event["contentStart"]
                    session._role = cs.get("role", "")
                    additional = cs.get("additionalModelFields", "")
                    if additional:
                        try:
                            af = _json.loads(additional)
                            session._capture_transcript = (
                                af.get("generationStage") == "SPECULATIVE"
                            )
                        except _json.JSONDecodeError:
                            session._capture_transcript = False

                elif "textOutput" in event:
                    text = event["textOutput"].get("content", "").strip()
                    role = event["textOutput"].get("role", session._role or "")
                    if text:
                        try:
                            await ws.send_json({
                                "type": "transcript",
                                "role": role,
                                "text": text,
                            })
                        except Exception:
                            return

                elif "audioOutput" in event:
                    b64_audio = event["audioOutput"].get("content", "")
                    if b64_audio:
                        try:
                            audio_bytes = base64.b64decode(b64_audio)
                            await ws.send_bytes(audio_bytes)
                        except Exception:
                            return

                elif "completionEnd" in event or "sessionEnd" in event:
                    session.is_active = False
                    break

            except StopAsyncIteration:
                session.is_active = False
                break
            except Exception as e:
                logger.warning(f"Interactive response stream error: {e}")
                continue

    except Exception as e:
        logger.error(f"Fatal interactive response error: {e}")
        session.is_active = False


# ═══════════════════════════════════════════════════════════════════════════════
# Web Reader Discussion Mode — Sonic discusses a simplified web page
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_webreader_websocket(ws: WebSocket, learner_id: str):
    """
    WebSocket handler for Web Reader discussion mode.
    Receives the page context (sonic_context from web_reader.py) and starts
    a Sonic session where Coach Nova discusses the page content with the student.
    """
    await ws.accept()
    logger.info(f"WebReader WS connected: learner={learner_id}")

    from core.interactive_session import InteractiveSonicSession

    session: InteractiveSonicSession = None
    response_task = None
    session_started = False

    try:
        await ws.send_json({"type": "status", "message": "connected"})

        while True:
            try:
                message = await ws.receive()
            except WebSocketDisconnect:
                break

            # Binary: PCM audio
            if message.get("bytes") is not None:
                if session_started:
                    await session._send_audio_chunk(message["bytes"])
                continue

            # Text: JSON control
            raw_text = message.get("text", "")
            if not raw_text:
                continue

            try:
                ctrl = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            msg_type = ctrl.get("type", "")

            if msg_type == "start_audio":
                page_context = ctrl.get("page_context", "")
                page_title = ctrl.get("page_title", "a web page")

                # Build a context string that tells Sonic about the page
                words_context = (
                    f"The student is reading a simplified web page titled '{page_title}'. "
                    f"Here is detailed context about the page content: {page_context}. "
                    f"Discuss this page with the student. Explain concepts simply, "
                    f"answer their questions about the content, and help them understand "
                    f"the key ideas. If they ask about a specific part, reference the content above."
                )

                # Fetch learner profile for personalization
                error_profile = {}
                try:
                    from storage.dynamo import get_learner_profile
                    profile = get_learner_profile(learner_id)
                    if profile:
                        error_profile = profile.get("error_profile", {})
                except Exception as e:
                    logger.warning(f"Could not fetch profile for web reader: {e}")

                session = InteractiveSonicSession(
                    learner_id=learner_id,
                    words_context=words_context,
                    error_profile=error_profile
                )
                try:
                    await session.start_streaming()
                    session_started = True
                    response_task = asyncio.create_task(
                        _stream_interactive_responses(ws, session)
                    )
                    await ws.send_json({"type": "status", "message": "listening"})
                except Exception as e:
                    logger.error(f"Failed to start web reader Sonic: {e}")
                    await ws.send_json({"type": "error", "message": str(e)})

            elif msg_type == "stop_audio":
                if not session_started:
                    continue
                try:
                    await session.stop_streaming()
                except Exception:
                    pass
                if response_task and not response_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(response_task), timeout=5.0)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        response_task.cancel()
                break

    except Exception as e:
        logger.error(f"WebReader WS error: {e}")
    finally:
        if session_started and session:
            try:
                session.is_active = False
                await session.stop_streaming()
            except Exception:
                pass
        if response_task and not response_task.done():
            response_task.cancel()
        logger.info(f"WebReader WS exiting: learner={learner_id}")


