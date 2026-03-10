"""
Nova Sonic Session
------------------
Handles the full bidirectional streaming session with Amazon Nova 2 Sonic.

SDK NOTE: This uses the experimental aws-sdk-bedrock-runtime package,
NOT standard boto3. Nova Sonic's InvokeModelWithBidirectionalStream API
is not available in boto3 yet.

Requires:
    pip install aws-sdk-bedrock-runtime smithy-aws-core
    Python 3.12+

What this does:
    1. Opens a bidirectional stream with Bedrock
    2. Sends initialization events (session config + system prompt)
    3. Receives mic audio chunks from caller → sends to Sonic
    4. Parses Sonic's output events → yields WordEvent objects
    5. Returns Sonic's audio output for playback (spoken word correction)
    6. Cleanly terminates the session

FIXES applied vs original:
    - contentBlockStart/contentBlockEnd → contentStart/contentEnd (correct SDK event names)
    - Config() no longer needs http_auth_scheme_resolver / http_auth_schemes args
    - asyncio.get_event_loop() → asyncio.get_running_loop() (Python 3.12+ / 3.14)
    - Added interactive:true to audio contentStart event
    - Stream close added on end_session
"""

import asyncio
import base64
import json
import uuid
import pyaudio
import time
from typing import List

# Experimental Bedrock SDK - required for bidirectional streaming
from aws_sdk_bedrock_runtime.client import (
    BedrockRuntimeClient,
    InvokeModelWithBidirectionalStreamOperationInput,
)
from aws_sdk_bedrock_runtime.models import (
    InvokeModelWithBidirectionalStreamInputChunk,
    BidirectionalInputPayloadPart,
)
from aws_sdk_bedrock_runtime.config import Config
from smithy_aws_core.identity.environment import EnvironmentCredentialsResolver

from schemas.session_trace import WordEvent
from config.settings import (
    AWS_REGION,
    SONIC_MODEL_ID,
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
    CHANNELS,
    CHUNK_SIZE,
)


# ── System prompt sent to Nova Sonic ─────────────────────────────────────────
SYSTEM_PROMPT = """You are Coach Nova, a helpful and patient reading buddy for a child with dyslexia.

YOUR INSTRUCTIONS:
1. Listen quietly and carefully while the child reads. Transcribe what they say accurately.
2. DO NOT speak or interrupt while they are reading. Just listen.
3. When the child completely finishes reading or says they are done, then you may speak.
4. Keep your spoken review very short, simple, and easy to understand.
5. Point out one word they did well, and gently explain how to correctly say one word they struggled with.
6. Use a very warm, supportive, and playful voice. Do not use big words."""


class NovaSonicSession:
    """
    Manages one reading session with Nova 2 Sonic.

    Usage:
        session = NovaSonicSession(learner_id="abc")
        word_events, duration = await session.run_reading_session(passage_text)
        # word_events is List[WordEvent] ready for trace_builder
    """

    def __init__(self, learner_id: str):
        self.learner_id = learner_id
        self.model_id = SONIC_MODEL_ID
        self.region = AWS_REGION
        self.prompt_name = str(uuid.uuid4())
        self.content_name = str(uuid.uuid4())
        self.audio_content_name = str(uuid.uuid4())

        self.client = None
        self.stream = None
        self.is_active = False
        self._capture_transcript = False
        self._role = None

        # Collected during session
        self.word_events: List[WordEvent] = []
        self.audio_output_queue = asyncio.Queue()

        # Timing
        self.session_start_time: float = 0.0
        self.last_word_end_ms: int = 0
        self.word_position: int = 0

    # ── Client init ───────────────────────────────────────────────────────────

    def _initialize_client(self):
        """
        Set up the experimental Bedrock client with SigV4 auth.
        Credentials are read from environment variables:
            AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
        
        FIX: Removed http_auth_scheme_resolver and http_auth_schemes — not needed
        per official AWS sample (nova_sonic_simple.py). EnvironmentCredentialsResolver
        handles auth automatically.
        """
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    # ── Event sending helpers ─────────────────────────────────────────────────

    async def _send_event(self, event_json: str):
        """Serialize a JSON string and send as a stream event."""
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(chunk)

    # ── Session lifecycle events ───────────────────────────────────────────────

    async def _send_session_start(self):
        await self._send_event(json.dumps({
            "event": {
                "sessionStart": {
                    "inferenceConfiguration": {
                        "maxTokens": 1024,
                        "topP": 0.9,
                        "temperature": 0.7
                    }
                }
            }
        }))

    async def _send_prompt_start(self):
        await self._send_event(json.dumps({
            "event": {
                "promptStart": {
                    "promptName": self.prompt_name,
                    "textOutputConfiguration": {
                        "mediaType": "text/plain"
                    },
                    "audioOutputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": OUTPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "voiceId": "tiffany",
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    }
                }
            }
        }))

    async def _send_system_prompt(self):
        """Send the system prompt as a text content block.
        
        FIX: contentBlockStart -> contentStart, contentBlockEnd -> contentEnd
        Also added textInputConfiguration.mediaType per official sample.
        """
        content_name = str(uuid.uuid4())
        # contentStart (was contentBlockStart — wrong)
        await self._send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "type": "TEXT",
                    "interactive": False,
                    "role": "SYSTEM",
                    "textInputConfiguration": {
                        "mediaType": "text/plain"
                    }
                }
            }
        }))
        await self._send_event(json.dumps({
            "event": {
                "textInput": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                    "content": SYSTEM_PROMPT
                }
            }
        }))
        # contentEnd (was contentBlockEnd — wrong)
        await self._send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name
                }
            }
        }))

    async def _start_audio_input(self):
        """Signal the start of user audio content block.
        
        FIX: contentBlockStart -> contentStart, added interactive:true
        """
        await self._send_event(json.dumps({
            "event": {
                "contentStart": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "type": "AUDIO",
                    "interactive": True,
                    "role": "USER",
                    "audioInputConfiguration": {
                        "mediaType": "audio/lpcm",
                        "sampleRateHertz": INPUT_SAMPLE_RATE,
                        "sampleSizeBits": 16,
                        "channelCount": 1,
                        "audioType": "SPEECH",
                        "encoding": "base64"
                    }
                }
            }
        }))

    async def _send_audio_chunk(self, pcm_bytes: bytes):
        """Encode one chunk of raw PCM audio and send to Sonic."""
        b64_audio = base64.b64encode(pcm_bytes).decode("utf-8")
        await self._send_event(json.dumps({
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": b64_audio
                }
            }
        }))

    async def _end_audio_input(self):
        """Signal end of audio content block.
        
        FIX: contentBlockEnd -> contentEnd
        """
        await self._send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name
                }
            }
        }))

    async def _end_prompt(self):
        await self._send_event(json.dumps({
            "event": {
                "promptEnd": {
                    "promptName": self.prompt_name
                }
            }
        }))

    async def _end_session(self):
        await self._send_event(json.dumps({
            "event": {
                "sessionEnd": {}
            }
        }))
        # FIX: close the stream after sending sessionEnd
        try:
            await self.stream.input_stream.close()
        except Exception:
            pass

    # ── Response processing ────────────────────────────────────────────────────

    async def _process_responses(self):
        """
        Consume the output stream from Nova Sonic.
        Parses textOutput events → WordEvent objects.
        Parses audioOutput events → queues for playback.
        """
        try:
            while self.is_active:
                try:
                    output = await self.stream.await_output()
                    result = await output[1].receive()

                    if not (result.value and result.value.bytes_):
                        continue

                    raw = result.value.bytes_.decode("utf-8")
                    data = json.loads(raw)

                    if "event" not in data:
                        continue

                    event = data["event"]

                    # ── contentStart: check role and if speculative ──
                    if "contentStart" in event:
                        content_start = event["contentStart"]
                        self._role = content_start.get("role", "")
                        additional = content_start.get("additionalModelFields", "")
                        if additional:
                            try:
                                af = json.loads(additional)
                                # SPECULATIVE = Sonic's transcript of what user said
                                self._capture_transcript = (
                                    af.get("generationStage") == "SPECULATIVE"
                                )
                            except json.JSONDecodeError:
                                self._capture_transcript = False

                    # ── Text output: learner's transcript ──
                    elif "textOutput" in event:
                        text = event["textOutput"].get("content", "").strip()
                        role = event["textOutput"].get("role", self._role or "")
                        # Only capture USER role text (transcript of learner reading)
                        if text and (role == "USER" or self._capture_transcript):
                            words = text.split()
                            for word in words:
                                if not word:
                                    continue
                                now_ms = int(
                                    (time.monotonic() - self.session_start_time) * 1000
                                )
                                confidence = event["textOutput"].get("confidence", 0.85)
                                word_event = WordEvent(
                                    word=word,
                                    position_index=self.word_position,
                                    start_time_ms=self.last_word_end_ms,
                                    end_time_ms=now_ms,
                                    confidence=float(confidence),
                                    flags=[]
                                )
                                self.word_events.append(word_event)
                                self.last_word_end_ms = now_ms
                                self.word_position += 1
                                logger.debug(f"Sonic Word: {word}")

                    # ── Audio output: Sonic speaking back ──
                    elif "audioOutput" in event:
                        b64_audio = event["audioOutput"].get("content", "")
                        if b64_audio:
                            audio_bytes = base64.b64decode(b64_audio)
                            await self.audio_output_queue.put(audio_bytes)

                    # ── Session completion ──
                    elif "completionEnd" in event or "sessionEnd" in event:
                        self.is_active = False
                        break

                except StopAsyncIteration:
                    self.is_active = False
                    break
                except Exception as e:
                    logger.error(f"Response handler error: {e}")
                    continue

        except Exception as e:
            logger.fatal(f"Fatal response error: {e}")
            self.is_active = False

    # ── Audio playback ─────────────────────────────────────────────────────────

    async def _play_audio_output(self):
        """Play Sonic's spoken responses back to the learner."""
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=OUTPUT_SAMPLE_RATE,
            output=True,
            frames_per_buffer=CHUNK_SIZE
        )
        try:
            while self.is_active or not self.audio_output_queue.empty():
                try:
                    audio_data = await asyncio.wait_for(
                        self.audio_output_queue.get(), timeout=0.5
                    )
                    # Write in chunks to avoid blocking the event loop
                    loop = asyncio.get_running_loop()  # FIX: was get_event_loop()
                    for i in range(0, len(audio_data), CHUNK_SIZE):
                        chunk = audio_data[i:i + CHUNK_SIZE]
                        await loop.run_in_executor(None, stream.write, chunk)
                        await asyncio.sleep(0.001)
                except asyncio.TimeoutError:
                    continue
        except Exception as e:
            logger.error(f"Audio playback error: {e}")
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

    # ── Microphone capture ─────────────────────────────────────────────────────

    async def _capture_and_stream_audio(self):
        """Capture mic audio and send to Nova Sonic in real time."""
        p = pyaudio.PyAudio()
        mic_stream = p.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=INPUT_SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK_SIZE
        )

        logger.info("Recording started via PyAudio")
        self.session_start_time = time.monotonic()

        await self._start_audio_input()

        stop_event = asyncio.Event()

        async def wait_for_enter():
            loop = asyncio.get_running_loop()  # FIX: was get_event_loop()
            await loop.run_in_executor(None, input)
            stop_event.set()

        enter_task = asyncio.create_task(wait_for_enter())

        try:
            while not stop_event.is_set() and self.is_active:
                loop = asyncio.get_running_loop()  # FIX: was get_event_loop()
                pcm_data = await loop.run_in_executor(
                    None,
                    lambda: mic_stream.read(CHUNK_SIZE, exception_on_overflow=False)
                )
                await self._send_audio_chunk(pcm_data)
                await asyncio.sleep(0.01)
        finally:
            enter_task.cancel()
            mic_stream.stop_stream()
            mic_stream.close()
            p.terminate()

        await self._end_audio_input()

    # ── WebSocket-compatible audio streaming ───────────────────────────────────

    async def start_streaming(self):
        """
        Initialize Sonic stream and send all setup events.
        Call this before feeding audio chunks via send_audio_chunk().
        Used by websocket_handler.py.
        """
        if not self.client:
            self._initialize_client()
        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True
        self.session_start_time = time.monotonic()
        await self._send_session_start()
        await self._send_prompt_start()
        await self._send_system_prompt()
        await self._start_audio_input()

    async def stop_streaming(self):
        """Signal end of audio and close session. Used by websocket_handler.py."""
        try:
            await self._end_audio_input()
            await self._end_prompt()
            await self._end_session()
        except Exception:
            pass
        self.is_active = False

    # ── Main session runner (CLI mode) ────────────────────────────────────────

    async def run_reading_session(self, passage_text: str) -> tuple[List[WordEvent], float]:
        """
        Full session lifecycle for CLI use (main.py).

        Returns:
            (word_events, duration_seconds)
        """
        if not self.client:
            self._initialize_client()

        logger.info("Connecting to Nova 2 Sonic...")

        self.stream = await self.client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self.model_id)
        )
        self.is_active = True
        logger.info("Sonic Connected")

        await self._send_session_start()
        await self._send_prompt_start()
        await self._send_system_prompt()

        session_wall_start = time.monotonic()

        # Start response processing in background
        response_task = asyncio.create_task(self._process_responses())

        try:
            await asyncio.gather(
                self._capture_and_stream_audio(),
                self._play_audio_output(),
            )
        except Exception as e:
            print(f"\n  [Session error: {e}]")
        finally:
            try:
                await self._end_prompt()
                await self._end_session()
            except Exception:
                pass
            self.is_active = False

        # Wait briefly for response task to finish
        try:
            await asyncio.wait_for(response_task, timeout=3.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            response_task.cancel()

        duration = time.monotonic() - session_wall_start
        logger.info(f"Session ended. Duration: {duration:.1f}s, Words captured: {len(self.word_events)}")

        return self.word_events, duration