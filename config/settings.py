import os
from dotenv import load_dotenv

load_dotenv()

# AWS Configuration
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
AUDIO_BUCKET = os.getenv("AUDIO_BUCKET")
VECTOR_BUCKET = os.getenv("VECTOR_BUCKET")

# Model IDs
SONIC_MODEL_ID = os.getenv("SONIC_MODEL_ID", "amazon.nova-2-sonic-v1:0")
LITE_MODEL_ID = os.getenv("LITE_MODEL_ID", "us.amazon.nova-2-lite-v1:0")
EMBEDDINGS_MODEL_ID = os.getenv("EMBEDDINGS_MODEL_ID", "amazon.nova-2-multimodal-embeddings-v1:0")

# DynamoDB Tables
DYNAMO_PROFILES_TABLE = os.getenv("DYNAMO_PROFILES_TABLE", "learner-profiles")
DYNAMO_SESSIONS_TABLE = os.getenv("DYNAMO_SESSIONS_TABLE", "session-traces")

# Audio Processing Settings
# Nova Sonic REQUIRES: 16kHz, 16-bit, mono PCM
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000   # Sonic returns 24kHz audio
CHANNELS = 1
CHUNK_SIZE = 1024            # ~64ms of audio per chunk at 16kHz

# Hesitation Detection Thresholds
HESITATION_PAUSE_MS = 800        # gap between words > this = hesitation
CONFIDENCE_THRESHOLD = 0.75      # word confidence below this = uncertain
REPETITION_WINDOW = 3            # check for repeated word within N words

# Phoneme patterns to track
# Simple substring match on word text - catches common dyslexia triggers
PHONEME_PATTERNS = {
    "bl_cluster":   ["bl"],
    "str_cluster":  ["str"],
    "spl_cluster":  ["spl"],
    "tion_suffix":  ["tion"],
    "ough_pattern": ["ough"],
    "ck_digraph":   ["ck"],
    "th_digraph":   ["th"],
    "vowel_team_ea":["ea"],
    "vowel_team_oo":["oo"],
    "silent_e":     ["ake","ile","ine","one","ute"],
}