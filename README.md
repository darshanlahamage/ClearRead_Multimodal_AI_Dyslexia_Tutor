<div align="center">
  <h1>ClearRead — Multimodal AI Dyslexia Tutor</h1>
  <p><strong>Built for the Amazon Nova Hackathon 2026</strong></p>
  <p><em>Empowering every child to read with confidence using Amazon Nova 2 Sonic, Lite, and Vision.</em></p>
</div>

---


## 🎯 The Problem

Dyslexia affects roughly **1 in 5 children**. The core challenge isn't a lack of intelligence or effort; it's a neurological difference in how the brain processes written language. Children with dyslexia struggle with:

1. **Phonological Decoding:** Difficulty mapping letters to their corresponding sounds (e.g., struggling with blends like "bl" or digraphs like "th").
2. **Visual Tracking:** Difficulty keeping their place on a line of text, often skipping words or reversing letters.
3. **Working Memory:** Difficulty retaining the context of a sentence while spending immense cognitive energy just decoding individual words.

**The Failure of Current Tools:**
Traditional literacy apps fail these learners because their feedback is **delayed** (grading you after a session ends), their content is **generic** (everyone gets the same text regardless of their specific phoneme struggles), and they exist in a **silo** (disconnected from the real-world texts a child actually wants to read).

ClearRead was built to solve these exact problems.

---

## 💡 The Solution: ClearRead

ClearRead is an **Integrated Adaptive Diagnostic Engine** disguised as a friendly, voice-driven AI reading tutor. It creates a **Multimodal Learning Loop** that listens, diagnoses, and adapts to a child's unique cognitive fingerprint in real-time.

### Core Innovative Features

#### 🎙️ 1. Live Interactive AI Tutor (The Core Engine)
ClearRead provides **instantaneous, voice-grounded feedback** using **Amazon Nova 2 Sonic**. 
- When a child reads aloud, ClearRead highlights words on the screen *exactly* as they are spoken.
- If a student stalls or hesitates on a difficult word (e.g., "butterfly"), the tutor doesn't just passively wait. It detects the hesitation in real-time and intervenes with a gentle, phonetic breakdown or an encouraging nudge (*"Let's break that down. But-ter-fly."*).
- **The Tech:** We achieve sub-100ms visual latency by exploiting Nova Sonic's **speculative transcription tokens**, allowing the UI to highlight text *ahead* of the final audio silence threshold.

#### 🖼️ 2. Multimodal Vision Practice (Bridging Physical & Digital)
Learning shouldn't be confined to predefined, boring stories. ClearRead lets children learn from the world around them.
- A student snaps a photo of a cereal box, a Lego instruction manual, or a Pokémon card.
- **Amazon Nova 2 Lite Vision** analyzes the scene, performs OCR on the text, and synthesizes a **Context-Grounded Reading Passage**.
- This custom passage is immediately injected into the Live Interactive Tutor. The student is now practicing reading using a story generated from the item sitting right in front of them, making learning deeply personal and highly engaging.

#### 🌐 3. Web Reader (Dyslexia-Friendly Web Browsing)
The internet is hostile to dyslexic readers—dense paragraphs, distracting layouts, and complex fonts.
- A student pastes any URL into ClearRead.
- **Amazon Nova 2 Lite** extracts the core content and rewrites it into a clean, dyslexia-friendly format (preserving essential structure, headings, and images).
- **Inline Sonic Discussion:** A persistent "Coach Nova" side panel allows the student to scroll through this simplified web page while having a live, bidirectional voice conversation about the content, asking questions and getting explanations in real-time.

#### 📊 4. Adaptive Cognitive Profiling (Longitudinal Tracking)
ClearRead doesn't just track right/wrong words; it builds a clinical-grade profile.
- After every session, **Amazon Nova 2 Lite (via Extended Thinking)** analyzes the precise timestamps and hesitation patterns of the reading trace.
- It categorizes errors into four clinical dimensions: **Phonological Decoding, Visual Tracking, Working Memory, and Fluency**.
- Using an **Exponential Moving Average (EMA)** algorithm, ClearRead dynamically updates the student's curriculum. If the profile indicates a struggle with "bl" sounds today, future generated passages and pronunciation drills will specifically target "blue", "blind", and "bright".

---

## 🏗️ Technical Architecture & Amazon Nova Integration

ClearRead employs a high-performance FastAPI backend orchestrating three distinct phases of Coach Nova's intelligence over WebSocket and REST APIs.

### 1. Real-Time Bidirectional Streaming (Nova 2 Sonic)
We utilize the experimental `aws-sdk-bedrock-runtime` to establish a bidirectional audio stream with **Amazon Nova 2 Sonic** via WebSocket.
- **Input:** 16kHz, 16-bit Mono PCM audio captured live from the browser.
- **Output:** 24kHz, 16-bit Mono PCM audio streamed directly to the browser's `AudioContext`.
- **The Speculative Advantage:** By parsing `additionalModelFields` for `generationStage == "SPECULATIVE"`, we achieve zero-lag frontend word highlighting, a critical feature for users with visual tracking difficulties.

### 2. Deep Diagnostic Reasoning (Nova 2 Lite - Extended Thinking)
We do not use simple classification. We feed a highly detailed, millisecond-resolution `ReadingSessionTrace` to **Amazon Nova 2 Lite**.
- **Extended Thinking Budget:** We allocate an 8,000-token thinking budget, allowing Nova Lite to reason over the *timing* and *relationships* between staggered words to differentiate between a simple pause for breath and a genuine cognitive decoding error (e.g., struggling specifically on consonant clusters).

### 3. Contextual Synthesis (Nova 2 Lite Vision)
For the Picture Reading feature, the `image` content block is sent to **Nova 2 Lite Vision**.
- The prompt instructs the model to dynamically incorporate the student's *known weak phoneme patterns* into the newly generated story based on the image, creating a tightly coupled feedback loop between diagnostics and content generation.

### 4. Semantic Content Matching (Nova 2 Embeddings)
We utilize **Amazon Nova 2 Multimodal Embeddings** to vectorize both the Learner Profile (their cognitive diagnostic text) and our Content Library.
- **Zone of Proximal Development (ZPD):** We query S3-backed vectors to recommend "Next Adventure" passages that fall within a precise Cosine Similarity range (e.g., 0.55 - 0.85). This ensures recommendations are neither too easy (boring) nor too hard (frustrating).

---

## 💾 Data & Persistence Strategy

ClearRead uses Amazon DynamoDB for high-speed, scaleable data storage:

- **`learner-profiles` Table:** 
  - Partition Key: `learner_id`
  - Stores longitudinal EMA-blended severity scores for the 4 cognitive dimensions.
  - Caches `recent_sessions` for rapid dashboard rendering.
- **`reading-sessions` Table:**
  - Partition Key: `learner_id`, Sort Key: `session_id`
  - Stores high-resolution traces capturing every `WordEvent` (start/end ms, confidence, phoneme flags) and `HesitationEvent` for future model retraining or parent/teacher review.

---

## 🌟 The Impact on Dyslexic Learners

| Traditional Literacy Tools | ClearRead |
|-------------------------|-----------|
| **Static Content** | Content is dynamically generated and adapted to the child's specific phoneme weaknesses. |
| **Delayed Feedback** | Real-time word highlighting and instantaneous vocal intervention as the child speaks. |
| **Siloed Environment** | Photograph anything in the real world or paste any URL → it instantly becomes a tailored reading lesson. |
| **Generic Corrections** | *“The word 'bright' starts with a 'br' blend. Try saying 'brr' then 'ight'. Br-ight!”* |
| **No Long-term Memory** | EMA-blended cognitive profiles track progress over time, ensuring practice is always in the Zone of Proximal Development. |

**The Real-World Loop:**
A child struggles with "bl" words → Nova Sonic detects the hesitation live → Nova Lite analyzes the trace and updates the profile → The next real-world photo they take generates a story emphasizing "bl" words to provide targeted practice. Over weeks, the severity score for that specific deficit drops.

---

## 🚀 Setup & Local Development

### 1. Prerequisites
- Python 3.10+
- AWS Account with **Amazon Bedrock** access (ensure the Amazon Nova 2 model suite is enabled).
- Two DynamoDB tables created (`learner-profiles` and `session-traces`) with `learner_id` as the Partition Key.

### 2. Environment Configuration
Create a `.env` file in the project root:

```bash
AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY="YOUR_SECRET_ACCESS_KEY"
AWS_REGION="us-east-1"

# Amazon Nova Model ARNs
LITE_MODEL_ID="us.amazon.nova-2-lite-v1:0"
SONIC_MODEL_ID="us.amazon.nova-2-sonic-v1:0"
EMBEDDINGS_MODEL_ID="us.amazon.nova-2-embed-multimodal-v1:0"

# DynamoDB Tables
DYNAMO_PROFILES_TABLE="learner-profiles"
DYNAMO_SESSIONS_TABLE="session-traces" 
```

### 3. Installation & Launch
```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Seed the vector index for content recommendations
python scripts/embed_content.py

# 4. Launch the FastAPI backend
uvicorn api.main:app --reload --port 8000
```

Navigate to `http://localhost:8000` to interact with Coach Nova.

---
<div align="center">
  <strong>ClearRead</strong> was built by Darshan Lahamage for the <strong>Amazon Nova Hackathon 2026</strong>.
</div>
