# ClearRead — Multimodal AI Dyslexia Tutor

> Built for the **Amazon Nova Hackathon 2026** · Powered by Amazon Nova 2 Sonic, Lite, and Vision

---

## The Problem We're Solving

Dyslexia affects roughly 1 in 5 children. The core challenge isn't intelligence — it's that the brain processes written language differently, struggling with **phonological decoding** (mapping letters to sounds), **visual tracking** (keeping place on a line), and **working memory** (retaining context across a sentence).

Current literacy tools fail dyslexic learners in three specific ways:

1. **Delayed Feedback** — Most apps grade you *after* you finish reading. By then, the moment is gone. A child who hesitates on "butterfly" needs help *right now*, not in a summary screen 5 minutes later.
2. **Generic Content** — Every student gets the same passages, same difficulty, same drills. A child struggling with "bl" consonant clusters gets the same practice as one struggling with "th" digraphs.
3. **No Multimodal Bridge** — Reading doesn't just happen in apps. No tool connects that physical-world text to a structured learning experience.

**ClearRead** was built to solve all three.

---

## What ClearRead Actually Does

ClearRead is a **real-time, voice-driven AI reading tutor** that listens to a child read aloud, diagnoses their specific cognitive error patterns, and adapts every future interaction to target those exact weaknesses. It's not a chatbot that happens to discuss reading — it's a **clinical-grade diagnostic engine** wrapped in a child-friendly voice interface.

### Core Features

| Feature | What It Does | Nova Model Used |
|---------|-------------|-----------------|
| 🎙️ **Live Reading Sessions** | Child reads a passage aloud; ClearRead highlights words in real-time as they speak, detects hesitations and mispronunciations instantly | **Nova 2 Sonic** (Bidirectional Stream) |
| 🧠 **Cognitive Error Profiling** | After each session, analyzes the full trace to categorize errors into 4 clinical dimensions with severity scores | **Nova 2 Lite** (Extended Thinking) |
| 🖼️ **Picture-to-Passage** | Child photographs any real-world text; ClearRead OCRs it, understands the scene, and generates a personalized reading passage from it | **Nova 2 Lite** (Vision / Multimodal) |
| 🤖 **Interactive AI Tutor** | Full speech-to-speech practice mode where Coach Nova has a live conversation, generating sentences that target exactly the phoneme patterns this specific child struggles with | **Nova 2 Sonic** (Speech-to-Speech) |
| 🌐 **Web Reader** | Paste any URL — ClearRead fetches the page, simplifies it with dyslexia-friendly formatting (adjustable font, spacing, colors), then lets you discuss it live with Coach Nova | **Nova 2 Lite** (Extended Thinking) + **Nova 2 Sonic** (Discussion) |
| 📊 **Adaptive Difficulty** | System automatically adjusts reading level based on longitudinal performance trends (WPM, accuracy, hesitation count) | **Nova 2 Lite** + EMA Algorithm |
| 🔍 **Content Recommendation (RAG)** | Embeds learner profiles and passages into vector space; recommends "next adventures" in the Zone of Proximal Development | **Nova 2 Multimodal Embeddings** + S3 Vectors |

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER (Frontend)                       │
│  Audio capture (16kHz PCM) ←→ WebSocket ←→ Word highlighting    │
│  Photo capture → REST API → Vision results display              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    WebSocket + REST
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI Backend (api/)                        │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ WebSocket   │  │ REST Routes  │  │ Static File Server     │  │
│  │ Handler     │  │ /api/*       │  │ (frontend/dist/)       │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────────┘  │
│         │                │                                      │
│  ┌──────▼────────────────▼──────────────────────────────────┐   │
│  │                  Core Engine (core/)                      │   │
│  │                                                          │   │
│  │  sonic_session.py ──── Bidirectional Sonic streaming      │   │
│  │  interactive_session.py ── Speech-to-speech practice      │   │
│  │  hesitation_detector.py ── Real-time signal analysis      │   │
│  │  trace_builder.py ──── Session trace assembly             │   │
│  │  lite_reasoner.py ──── Extended thinking diagnosis        │   │
│  │  text_adapter.py ──── Passage adaptation + micro-drills   │   │
│  │  vision_reader.py ──── Image → passage generation         │   │
│  │  web_reader.py ──── URL → dyslexia-friendly content       │   │
│  │  embedder.py ──── Profile/content vectorization           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  Storage Layer (storage/)                 │   │
│  │  dynamo.py ──── Learner profiles + session traces         │   │
│  │  vectors.py ──── S3 Vectors for RAG recommendations       │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                           │
              ┌────────────▼────────────────┐
              │     AWS Services             │
              │                              │
              │  Amazon Bedrock              │
              │   ├── Nova 2 Sonic           │
              │   ├── Nova 2 Lite            │
              │   └── Nova 2 Embeddings      │
              │                              │
              │  DynamoDB                    │
              │   ├── learner-profiles       │
              │   └── session-traces         │
              │                              │
              │  S3 Vectors                  │
              │   ├── learner-ability-index   │
              │   └── content-library-index  │
              └──────────────────────────────┘
```

---

## Deep Dive: How Each Nova Model Is Used

### 1. Nova 2 Sonic — Real-time Bidirectional Streaming

This is the backbone. We use the **experimental `aws-sdk-bedrock-runtime`** SDK (not standard boto3) because Nova Sonic requires `InvokeModelWithBidirectionalStream`, which isn't available in boto3 yet.

**The Speculative Transcription Trick:**

Most speech-to-text systems wait for silence before "finalizing" a transcript. Nova Sonic is different — it emits **speculative outputs** via `additionalModelFields` in `contentStart` events. We check for `generationStage == "SPECULATIVE"` and immediately forward those tokens to the frontend.

```python
# From sonic_session.py — the key insight
additional = content_start.get("additionalModelFields", "")
if additional:
    af = json.loads(additional)
    self._capture_transcript = (
        af.get("generationStage") == "SPECULATIVE"
    )
```

**Why this matters for dyslexia:** A child reading "but-ter-fly" needs the word to highlight *as they say each syllable*, not after a 500ms silence. Speculative tokens give us ~100ms latency between speech and visual feedback — fast enough to feel instantaneous.

**Audio Pipeline:**
- Input: 16kHz, 16-bit, mono PCM (browser MediaRecorder → WebSocket → Sonic)
- Output: 24kHz, 16-bit, mono PCM (Sonic → WebSocket → browser AudioContext)
- Both streams run concurrently via `asyncio` tasks

### 2. Nova 2 Lite — Extended Thinking Diagnostic Engine

After a reading session, we have a `ReadingSessionTrace` containing every `WordEvent` (word, position, start/end timestamps, confidence score, phoneme flags). We feed a **summarized** version of this trace to Nova 2 Lite with extended thinking enabled.

**Why extended thinking?** Categorizing reading errors isn't a simple classification task. The model needs to reason about *relationships*: "The child hesitated on 'blue' AND 'black' AND 'blend' — these all share the 'bl' consonant cluster. This is a phonological decoding deficit, not a fluency issue."

We give the model an 8,000-token thinking budget:

```python
response = _bedrock.converse(
    modelId=LITE_MODEL_ID,
    messages=[{"role": "user", "content": [{"text": prompt}]}],
    additionalModelRequestFields={
        "thinking": {"type": "enabled", "budget_tokens": 8000}
    },
)
```

**Output structure — the 4 clinical dimensions:**

| Dimension | What It Measures | Example Pattern |
|-----------|-----------------|-----------------|
| `phonological_decoding` | Sound-letter mapping accuracy | `bl_cluster`, `th_digraph`, `silent_e` |
| `visual_tracking` | Ability to maintain reading position | `line_skip`, `word_reversal` |
| `working_memory` | Context retention across sentences | `long_sentence_loss` |
| `fluency` | Reading rhythm and prosody | `choppy_reading`, `monotone` |

Each dimension gets a severity score (1.0–10.0), pattern list, and confidence value. These are blended with the learner's historical profile using **Exponential Moving Average (EMA)** — `alpha = 0.3`, meaning each new session contributes 30% and history retains 70%.

### 3. Nova 2 Lite Vision — Turning the Real World Into Reading Lessons

The Picture Reading feature sends an image to Nova 2 Lite via the Converse API's `image` content block:

```python
response = _bedrock.converse(
    modelId=LITE_MODEL_ID,
    messages=[{
        "role": "user",
        "content": [
            {"image": {"format": "jpeg", "source": {"bytes": image_bytes}}},
            {"text": prompt_text}
        ]
    }],
)
```

The prompt instructs Nova to:
1. **Describe** the scene (2-3 sentences)
2. **OCR** any visible text
3. **Generate** a reading passage inspired by the image, adapted to the student's reading level and targeting their weak phoneme patterns

**The magic:** The generated passage + detected text are then passed as `words_context` to the Interactive Practice session. So when Coach Nova starts talking, it already knows the child just photographed a Lego box and can say: *"I see you took a picture of something cool! Let's try reading the words on it together."*

### 4. Nova 2 Multimodal Embeddings — Semantic Content Matching

We convert each learner profile into a diagnostic text description, then embed it into a 1024-dimension vector. We do the same for each reading passage in our content library.

**The Zone of Proximal Development (ZPD) filter:**

We don't just recommend the most similar content — we filter to a cosine similarity range of **0.55–0.85**. Too similar (>0.85) means the passage is too easy. Too different (<0.55) means it's too hard. The sweet spot is where real learning happens.

```python
MIN_SIMILARITY = 0.55  # Not too easy
MAX_SIMILARITY = 0.85  # Not too hard
```

---

## Prompt Engineering Strategies

We use carefully designed prompts throughout the system. Here are the key strategies:

1. **Summarize, Don't Dump** — The diagnostic prompt in `lite_reasoner.py` doesn't send raw JSON. It pre-processes the trace into human-readable sections (top hesitations, low-confidence words, phoneme flags) to keep the prompt under ~2000 tokens.

2. **Schema-Enforced Output** — Every prompt includes an explicit JSON schema example. We also have multi-layer JSON extraction: try direct parse → try regex `{...}` extraction → try array `[...]` extraction → fallback to defaults.

3. **Profile-Aware Vision** — The vision prompt dynamically includes the student's weak patterns: *"If the student has specific weak phoneme patterns (bl_cluster, th_digraph), try to include words with those sounds."*

4. **Mode-Switched Interactive Tutor** — The interactive session uses different system prompt instructions depending on whether it was triggered from the standard practice mode or from the Picture Reading feature. Vision mode gets: *"Start by greeting the student warmly. EXPLICITLY mention the picture they just took!"*

---

## DynamoDB Schema Design

### Table: `learner-profiles`

| Key | Type | Description |
|-----|------|-------------|
| `learner_id` (PK) | String | Unique student identifier |
| `created_at` | String (ISO8601) | Profile creation timestamp |
| `session_count` | Number | Total completed sessions |
| `current_difficulty_band` | String | `grade_1`, `grade_2`, `grade_3` |
| `phonological_decoding` | Map | `{severity, patterns[], confidence, session_count}` |
| `visual_tracking` | Map | Same structure |
| `working_memory` | Map | Same structure |
| `fluency` | Map | Same structure |
| `recent_sessions` | List (max 10) | Compact session summaries for dashboard charts |
| `coach_feedback` | Map | Latest feedback from Nova Lite analysis |

### Table: `session-traces`

| Key | Type | Description |
|-----|------|-------------|
| `learner_id` (PK) | String | Partition key |
| `session_id` (SK) | String | Sort key (UUID) |
| `word_events` | List | Every word: `{word, position, start_ms, end_ms, confidence, flags[]}` |
| `hesitation_events` | List | Detected pauses: `{after_word_index, pause_duration_ms, type}` |
| `aggregate_metrics` | Map | WPM, accuracy, hesitation count, flagged patterns |

---

## How This Impacts Dyslexic Kids

| Traditional Tool | ClearRead |
|-----------------|-----------|
| Same content for everyone | Content adapted to YOUR specific phoneme weaknesses |
| Feedback after the session | Real-time word highlighting as you speak |
| Only works with predefined texts | Photograph anything → it becomes a reading lesson |
| Generic "try again" corrections | *"The word 'bright' starts with a 'br' blend. Try saying 'brr' then 'ight'. Br-ight!"* |
| No longitudinal tracking | EMA-blended cognitive profiles across sessions, with progress charts |
| Practice = repeat the same thing | Practice = targeted drills on exactly the sounds you struggle with |

**The feedback loop that matters:**

```
Read → ClearRead detects hesitation on "bl" words
     → Nova Lite categorizes: phonological_decoding severity 7.2
     → Next session: passage is adapted, "bl" words simplified
     → Micro-drills generated: "Say b...l...ue. Now blend: blue!"
     → Interactive tutor specifically generates sentences with "bl" words
     → Over 5 sessions: severity drops from 7.2 → 4.1
     → Content recommendation shifts to harder passages
```

---

## Screenshots

### Dashboard & Progress Charts
*(Add screenshot: WPM and Accuracy trend charts with the 4-category cognitive skill breakdown)*

### Live Reading Session
*(Add screenshot: Reading view with real-time word highlighting, passage text, and the recording controls)*

### Picture Reading (Vision)
*(Add screenshot: Image upload interface showing the captured photo alongside the generated passage and detected text)*

### Interactive Practice with Coach Nova
*(Add screenshot: Speech-to-speech conversation view with the image context displayed alongside)*

### Web Reader
*(Add screenshot: URL input and simplified page with customization controls — font size, spacing, color theme selectors)*

---

## Setup & Run

### Prerequisites
- Python 3.10+
- AWS account with Amazon Bedrock access (Nova 2 models enabled)
- DynamoDB tables created (see schema above)

### Environment Variables

Create a `.env` file in the project root:

```bash
AWS_ACCESS_KEY_ID="your_access_key"
AWS_SECRET_ACCESS_KEY="your_secret_key"
AWS_DEFAULT_REGION=us-east-1

LITE_MODEL_ID=us.amazon.nova-2-lite-v1:0
SONIC_MODEL_ID=amazon.nova-2-sonic-v1:0
EMBEDDINGS_MODEL_ID=amazon.nova-2-multimodal-embeddings-v1:0

DYNAMO_PROFILES_TABLE=learner-profiles
DYNAMO_SESSIONS_TABLE=session-traces

VECTOR_BUCKET=your-s3-vectors-bucket-name
```

### Installation

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# (One-time) Embed reading passages into vector index
python scripts/embed_content.py

# (Optional) Seed demo data for showcasing progress charts
python scripts/seed_demo.py
```

### Run

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000` in your browser. That's it.

---

**Built by Darshan Lahamage** · Amazon Nova Hackathon 2026
