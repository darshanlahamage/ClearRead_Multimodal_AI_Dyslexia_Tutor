"""
Interactive Sonic Session
--------------------------
A separate Nova Sonic session used for Interactive Practice mode.
Unlike the assessment session (which mutes Sonic's voice), this session
enables full speech-to-speech: Coach Nova speaks freely, generates sentences
for the student to practice, corrects pronunciation, and answers questions.

Uses the same experimental aws-sdk-bedrock-runtime SDK as sonic_session.py.
"""

import asyncio
import base64
import json
import uuid
import time
from typing import List

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

from config.settings import (
    AWS_REGION,
    SONIC_MODEL_ID,
    INPUT_SAMPLE_RATE,
    OUTPUT_SAMPLE_RATE,
    CHANNELS,
    CHUNK_SIZE,
)

import logging
logger = logging.getLogger(__name__)


INTERACTIVE_BASE_PROMPT = """You are Coach Nova, an enthusiastic and patient AI reading tutor for children with dyslexia.

You are in INTERACTIVE PRACTICE MODE. This is a back-and-forth voice conversation.

STUDENT'S COGNITIVE PROFILE (from their real reading assessments):
{error_profile_context}

{words_context}

YOUR BEHAVIOR — THIS IS WHAT MAKES YOU DIFFERENT FROM A GENERIC AI:
1. You have REAL DATA about this specific student's reading struggles (above). Use it!
{mode_specific_instructions}
4. After the student speaks, listen carefully and correct mispronounced words gently.
   - Explain HOW to say it using simple phonics rules
   - Break difficult words into syllables (e.g., "but-ter-fly — three parts!")
5. If the student says it correctly, praise them enthusiastically! Be SPECIFIC about what they got right.
6. If the student asks a question, answer it patiently.
7. Keep language SIMPLE. You are talking to a child. Be playful and fun.

REMEMBER: A generic chatbot gives random practice. YOU target THIS student's specific weaknesses based on the context above.
You are having a LIVE CONVERSATION. Speak naturally, take turns, and ask the student a question to keep them engaged."""

STANDARD_INSTRUCTIONS = """2. Start by greeting the student warmly. Mention that you noticed they're working on specific sounds.
3. Generate SHORT sentences (5-8 words) that SPECIFICALLY CONTAIN the phoneme patterns this student struggles with.
   - If they struggle with 'bl_cluster', make sentences with "blue", "black", "blink", "blend"
   - If they struggle with 'th_digraph', use "the", "this", "that", "three", "through"
   - If they struggle with 'str_cluster', use "strong", "street", "string", "stream" """

VISION_INSTRUCTIONS = """2. Start by greeting the student warmly. EXPLICITLY mention the picture they just took! "I see you took a picture of..."
3. Your goal is to discuss the picture AND practice reading the text or passage associated with it. 
   - Ask them what they see in the picture.
   - Ask them to try reading the words that were in the picture.
   - Help them tie the words in the picture to the phonics patterns they are working on."""


class InteractiveSonicSession:
    """
    Manages a bidirectional speech session with Nova Sonic for interactive practice.
    Unlike NovaSonicSession, this SENDS audio output back to the browser.
    """

    def __init__(self, learner_id: str, words_context: str = "", error_profile: dict = None):
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

        self.words_context = words_context
        self.error_profile = error_profile or {}
        self.session_start_time: float = 0.0

    def _initialize_client(self):
        config = Config(
            endpoint_uri=f"https://bedrock-runtime.{self.region}.amazonaws.com",
            region=self.region,
            aws_credentials_identity_resolver=EnvironmentCredentialsResolver(),
        )
        self.client = BedrockRuntimeClient(config=config)

    async def _send_event(self, event_json: str):
        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(bytes_=event_json.encode("utf-8"))
        )
        await self.stream.input_stream.send(chunk)

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
        content_name = str(uuid.uuid4())

        # Build error profile context from student's real assessment data
        error_profile_context = ""
        if self.error_profile:
            lines = []
            skill_map = {
                'phonological_decoding': 'Sounding Out Words',
                'visual_tracking': 'Keeping Their Place',
                'working_memory': 'Remembering the Story',
                'fluency': 'Reading Smoothly'
            }
            for cat, label in skill_map.items():
                cat_data = self.error_profile.get(cat)
                if cat_data:
                    sev = cat_data.get('severity', 5.0)
                    patterns = cat_data.get('patterns', [])
                    if sev >= 6.0:
                        level = "STRUGGLES WITH"
                    elif sev >= 4.0:
                        level = "working on"
                    else:
                        level = "good at"
                    pat_str = ', '.join(patterns) if patterns else 'general'
                    lines.append(f"- {label}: {level} (severity {sev:.1f}/10, patterns: {pat_str})")
            
            low_conf = self.error_profile.get('low_confidence_words', [])
            if low_conf:
                lines.append(f"- Words they struggled with recently: {', '.join(low_conf[:10])}")
            
            error_profile_context = '\n'.join(lines) if lines else 'No prior assessment data available — use general practice.'
        else:
            error_profile_context = 'No prior assessment data available — use general practice.'

        # Select instructions based on context type
        if "took a picture of" in self.words_context:
            mode_specific_instructions = VISION_INSTRUCTIONS
        else:
            mode_specific_instructions = STANDARD_INSTRUCTIONS

        prompt_text = INTERACTIVE_BASE_PROMPT.format(
            error_profile_context=error_profile_context,
            words_context=self.words_context,
            mode_specific_instructions=mode_specific_instructions
        )

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
                    "content": prompt_text,
                }
            }
        }))

        await self._send_event(json.dumps({
            "event": {
                "contentEnd": {
                    "promptName": self.prompt_name,
                    "contentName": content_name,
                }
            }
        }))

    async def _start_audio_input(self):
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
                        "channelCount": CHANNELS,
                        "encoding": "base64",
                        "audioType": "SPEECH"
                    }
                }
            }
        }))

    async def _send_audio_chunk(self, pcm_bytes: bytes):
        if not self.is_active:
            return
        b64 = base64.b64encode(pcm_bytes).decode("utf-8")
        await self._send_event(json.dumps({
            "event": {
                "audioInput": {
                    "promptName": self.prompt_name,
                    "contentName": self.audio_content_name,
                    "content": b64,
                }
            }
        }))

    async def start_streaming(self):
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

        logger.info(f"Interactive Sonic session started for {self.learner_id}")

    async def stop_streaming(self):
        if not self.is_active:
            return
        self.is_active = False
        try:
            await self._send_event(json.dumps({
                "event": {
                    "contentEnd": {
                        "promptName": self.prompt_name,
                        "contentName": self.audio_content_name,
                    }
                }
            }))
            await self._send_event(json.dumps({
                "event": {
                    "promptEnd": {
                        "promptName": self.prompt_name,
                    }
                }
            }))
            await self._send_event(json.dumps({
                "event": {
                    "sessionEnd": {}
                }
            }))
            await self.stream.input_stream.close()
        except Exception as e:
            logger.warning(f"Error closing interactive stream: {e}")
