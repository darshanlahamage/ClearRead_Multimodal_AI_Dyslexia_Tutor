# ClearRead: Multimodal AI Dyslexia Tutor

## 1. The Core Mission
Reading is a foundational cognitive skill, yet millions of children with dyslexia face a "leaky bucket" problem: they practice, but without immediate, phoneme-level feedback, their errors solidify. Current digital tools are either too generic or lack the real-time presence of a human coach.

**ClearRead** is our answer to this challenge ; it is an **Integrated Adaptive Diagnostic Engine**. built it to bridge the gap between **Nova capabilities** and **human-centered literacy coaching**, providing dyslexic kids with a personalized tutor that listens, understands, and adapts to their specific cognitive fingerprint.

---

## 2. Integrated Solution & Core Features

This solution revolves around the concept of a **"Multimodal Learning Loop."** We use the **Amazon Nova 2** family of models not as isolated features, but as a cohesive intelligence layer that tracks a student across distinct learning modes.

### 🎙️ The Interactive AI Tutor (The Heart of ClearRead)
Our project features a **Speculative Real-time Coach**. 
- **Voice-Grounded Learning**: Using **Nova 2 Sonic**, the tutor provides instantaneous feedback. If a student stalls on a word like "butterfly," the tutor doesn't just wait; it identifies the hesitation in real-time and provides a rhythmic nudge or a phonetic breakdown.
- **Speculative Transcription**: We exploit Sonic’s speculative tokens to highlight the text *ahead* of finalization, creating a seamless, game-like experience where the interface "ghosts" the user's voice with 100ms latency.

### 🖼️ Multimodal Vision Practice (Bringing the World to the App)
We believe learning shouldn't be confined to predefined stories.
- **Physical-to-Digital Leap**: A student can take or upload a photo of a cereal box, a Lego instruction manual, or a page from their favorite book. 
- **Nova 2 Lite Vision Pipeline**: The system OCRs the text and analyzes the scene to synthesize a **Context-Grounded Passage**.
- **The Magic Trace**: This generated passage is then immediately injected into the Interactive Tutor mode. The student is now practicing with a story *they* found in their own room, making the learning experience deeply personal and rewarding.

### 🌐 Web Reader (Dyslexia-Friendly Web)
The web can be overwhelming with dense text and distracting layouts.
- **Content Simplification**: A student can paste any URL, and **Nova 2 Lite** extracts and rewrites the content into a clean, dyslexia-friendly format (preserving headings, lists, and images).
- **Inline Sonic Discussion**: A persistent, floating "Coach Nova" side panel allows the student to scroll through the simplified web page while having a live, real-time voice conversation about the content.

### 📊 Adaptive User Profile (The Longitudinal Brain)
Every mistake a student makes—a hesitation, a repetition, a low-confidence word—is captured in our **Cognitive Error Profile**.
- **Clinical Categorization**: Using Nova 2 Lite's Extended Thinking, we categorize errors into 4 dimensions: Phonological Decoding, Visual Tracking, Working Memory, and Fluency.
- **Dynamic Curriculum**: As the profile evolves via our **EMA (Exponential Moving Average) algorithm**, the app dynamically adjusts. If you're struggling with "bl" sounds today, your next practice sessions in future will be automatically populated with "blue," "bright," and "blind" , etc drills.

---

## 3. Technical Architecture & Component Flow

The system is built on a high-availability FastAPI backend orchestrating three distinct phases of "Coach Nova's" intelligence.

### 1. Real-time Response & Speculative Highlighting
We utilize **Amazon Nova 2 Sonic** via a bidirectional WebSocket for sub-second latency.
- **Technique**: We parse the `additionalModelFields` to extract `generationStage == "SPECULATIVE"`. 
- **Impact**: This ensures the frontend highlight never "lags" the user's voice, maintained via a raw PCM 16-bit 16kHz stream.

### 2. Extended Thinking Diagnostic (Analysis)
Once a session ends, the raw `json_trace` is passed to **Amazon Nova 2 Lite**.
- **Reasoning Loop**: Nova Lite doesn't just count errors; it reasons over the *timing* between words to differentiate between a simple pause and a cognitive tracking error.

### 3. Contextual Personalization (Multimodal Vision & Web)
- **The Scene Loop**: Leverages Nova 2 Lite Vision to synthesize context from images, or Nova 2 Lite to simplify URL content.
- **The Integration**: The context is fed into the Interactive Practice mode, allowing "Coach Nova" to have a naturally grounded conversation about the image or web page the student is currently viewing.

---

## 4. Data & Persistence Strategy

### DynamoDB Schema
- **`learner-profiles`**: 
  - `PK: learner_id`
  - Stores the longitudinal EMA-blended severity scores and the `recent_sessions` (last 10) for high-speed dashboard rendering.
- **`reading-sessions`**:
  - `PK: learner_id`, `SK: session_id`
  - Stores high-resolution traces capturing every `WordEvent` (start/end ms, confidence, phoneme flags).

### Vector RAG
We use **Amazon Nova Multimodal Embeddings** to convert learner profiles into 1024-dimension vectors. This allows us to query an S3-backed index of content to suggest the "Next Adventure" that best matches the student's current cognitive needs.

---

## 5. Setup & Development

### .env Configuration
\`\`\`bash
AWS_ACCESS_KEY_ID="YOUR_ACCESS_KEY_ID"
AWS_SECRET_ACCESS_KEY="YOUR_SECRET_ACCESS_KEY"
AWS_REGION=us-east-1

LITE_MODEL_ID=us.amazon.nova-2-lite-v1:0
SONIC_MODEL_ID=us.amazon.nova-2-sonic-v1:0
EMBEDDINGS_MODEL_ID=us.amazon.nova-2-embed-multimodal-v1:0

DYNAMO_PROFILES_TABLE="YOUR_DYNAMO_PROFILES_TABLE"
DYNAMO_SESSIONS_TABLE="YOUR_DYNAMO_SESSION_TABLE" 
\`\`\`

### Installation & Run
1. **Infra**: Setup DynamoDB with \`learner_id\` as Partition Key.
2. **Setup**: \`pip install -r requirements.txt\`
3. **Seed**: \`python scripts/embed_content.py\` (One-time setup for recommendations)
4. **Launch**: \`uvicorn api.main:app --reload --port 8000\`

---
**Submission for Amazon Nova Hackathon 2026**
"Empowering every child to read with confidence."