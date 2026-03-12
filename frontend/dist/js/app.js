// ClearRead AI - Core Application Logic

const AppState = {
    learnerId: null,
    passages: [],
    currentPassage: null,
    ws: null,
    audioContext: null,
    mediaStream: null,
    isRecording: false,
    sessionData: null,
    useDyslexicFont: true
};

// API Helpers
const API_BASE = window.location.origin.includes('localhost') ? 'http://localhost:8000/api' : '/api';
const WS_BASE = window.location.origin.includes('localhost')
    ? 'ws://localhost:8000/ws'
    : `ws://${window.location.host}/ws`;

async function fetchAPI(endpoint, options = {}) {
    try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options
        });
        if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
        return await res.json();
    } catch (e) {
        console.error(e);
        return null;
    }
}

// Routing & Rendering

function renderLoading() {
    const container = document.getElementById('app-container');
    container.innerHTML = `
        <div class="flex-grow flex flex-col items-center justify-center animate-pulse">
            <div class="w-16 h-16 rounded-full border-4 border-primary border-t-transparent animate-spin mb-4"></div>
            <p class="text-slate-400 font-medium tracking-wide">AI is analyzing...</p>
        </div>
    `;
}

const app = {
    async init() {
        // Hydrate learner from localStorage
        const savedLearner = localStorage.getItem('clearread_learner');
        if (savedLearner) {
            AppState.learnerId = savedLearner;
            document.getElementById('user-profile-badge').classList.remove('hidden');
            document.getElementById('header-learner-id').innerText = savedLearner;
        }

        // Pre-fetch passages
        const p = await fetchAPI('/passages');
        if (p) AppState.passages = p;

        // Route to home
        this.navigate('home');
    },

    navigate(view, payload = null) {
        const container = document.getElementById('app-container');
        container.classList.remove('animate-fade-in');

        // Hide interactive view if leaving
        if (view !== 'practice') {
            const iv = document.getElementById('interactive-view');
            if (iv) iv.classList.add('hidden');
        }

        // Triggers re-flow to restart animation
        void container.offsetWidth;

        container.classList.add('animate-fade-in');

        switch (view) {
            case 'home': this.renderHome(container); break;
            case 'session': this.renderSession(container, payload); break;
            case 'results': this.renderResults(container, payload); break;
            case 'progress': this.renderProgress(container, payload); break;
            case 'practice': this.renderPractice(container, payload); break;
            case 'picture-read': this.renderPictureReading(container); break;
            case 'web-reader': this.renderWebReader(container); break;
        }
    },

    // Views

    renderHome(container) {
        let passagesHtml = '';
        const sorted = [...AppState.passages].sort((a, b) => a.difficulty_band.localeCompare(b.difficulty_band));

        sorted.forEach(p => {
            const level = p.difficulty_band.replace('grade_', 'Grade ');
            passagesHtml += `
                <div class="glass-card p-6 flex flex-col justify-between hover:border-primary/50 cursor-pointer group"
                     onclick="app.startSession('${p.passage_id}')">
                    <div>
                        <div class="flex justify-between items-start mb-4">
                            <span class="text-xs font-bold px-3 py-1 bg-white rounded-full text-primary border border-primary/20">
                                ${level}
                            </span>
                            <i data-lucide="book-open" class="text-slate-400 group-hover:text-primary transition-colors"></i>
                        </div>
                        <h3 class="text-xl font-bold mb-2 text-slate-800 group-hover:text-black">${p.title}</h3>
                        <p class="text-sm text-slate-500 line-clamp-3">${p.text}</p>
                    </div>
                    <div class="mt-6 flex items-center gap-2 text-sm font-medium text-primary opacity-0 group-hover:opacity-100 transition-opacity">
                        Start reading <i data-lucide="arrow-right" class="w-4 h-4"></i>
                    </div>
                </div>
            `;
        });

        const learnerUI = AppState.learnerId
            ? `<div class="mb-6 flex gap-4">
                 <button onclick="app.switchUser()" class="text-slate-500 hover:text-slate-800 text-sm px-4">Switch User</button>
               </div>`
            : `<div class="mb-8 glass-panel p-6 rounded-2xl max-w-sm">
                 <h2 class="text-lg font-bold text-slate-800 mb-3">Who is reading today?</h2>
                 <div class="flex gap-2">
                   <input type="text" id="login-id" placeholder="Enter username (e.g. demo_learner_001)" 
                          class="bg-white border-slate-200 rounded-lg px-4 py-2 w-full focus:outline-none focus:border-primary text-sm text-slate-900 shadow-sm">
                   <button onclick="app.login()" class="bg-primary hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium transition-colors">Go</button>
                 </div>
               </div>`;

        // Mode cards (only show if logged in)
        const modeCards = AppState.learnerId ? `
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 mb-10">
                <!-- Guided Reading -->
                <div class="glass-card p-5 border-indigo-200/50 hover:border-indigo-400 cursor-pointer group transition-all hover:scale-[1.02] hover:shadow-xl" onclick="document.getElementById('library-section').scrollIntoView({behavior:'smooth'})">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-500 to-blue-600 flex items-center justify-center shadow-md shadow-indigo-500/30">
                            <i data-lucide="book-open" class="w-5 h-5 text-white"></i>
                        </div>
                        <h3 class="text-lg font-black text-slate-900">Guided Reading</h3>
                    </div>
                    <p class="text-sm text-slate-500 leading-relaxed">Read aloud with real-time word-by-word feedback from Coach Nova.</p>
                    <div class="mt-3 flex items-center gap-1 text-xs font-bold text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        Choose a story <i data-lucide="arrow-down" class="w-3 h-3"></i>
                    </div>
                </div>

                <!-- Interactive Practice -->
                <div class="glass-card p-5 border-purple-200/50 hover:border-purple-400 cursor-pointer group transition-all hover:scale-[1.02] hover:shadow-xl" onclick="app.navigate('practice')">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center shadow-md shadow-purple-500/30">
                            <i data-lucide="mic" class="w-5 h-5 text-white"></i>
                        </div>
                        <h3 class="text-lg font-black text-slate-900">Practice with AI</h3>
                    </div>
                    <p class="text-sm text-slate-500 leading-relaxed">Live voice conversation with Coach Nova. Practice tricky words.</p>
                    <div class="mt-3 flex items-center gap-1 text-xs font-bold text-purple-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        Start talking <i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </div>
                </div>

                <!-- Progress -->
                <div class="glass-card p-5 border-emerald-200/50 hover:border-emerald-400 cursor-pointer group transition-all hover:scale-[1.02] hover:shadow-xl" onclick="app.navigate('progress', '${AppState.learnerId}')">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-md shadow-emerald-500/30">
                            <i data-lucide="trending-up" class="w-5 h-5 text-white"></i>
                        </div>
                        <h3 class="text-lg font-black text-slate-900">My Progress</h3>
                    </div>
                    <p class="text-sm text-slate-500 leading-relaxed">Track speed, accuracy, and skill growth with visual charts.</p>
                    <div class="mt-3 flex items-center gap-1 text-xs font-bold text-emerald-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        View dashboard <i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </div>
                </div>

                <!-- Picture Reading -->
                <div class="glass-card p-5 border-amber-200/50 hover:border-amber-400 cursor-pointer group transition-all hover:scale-[1.02] hover:shadow-xl" onclick="app.navigate('picture-read')">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-md shadow-amber-500/30">
                            <i data-lucide="camera" class="w-5 h-5 text-white"></i>
                        </div>
                        <h3 class="text-lg font-black text-slate-900">Picture Reading</h3>
                    </div>
                    <p class="text-sm text-slate-500 leading-relaxed">Snap a photo of any text. Nova Vision turns it into a reading lesson.</p>
                    <div class="mt-3 flex items-center gap-1 text-xs font-bold text-amber-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        Try it now <i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </div>
                </div>

                <!-- Web Reader -->
                <div class="glass-card p-5 border-teal-200/50 hover:border-teal-400 cursor-pointer group transition-all hover:scale-[1.02] hover:shadow-xl" onclick="app.navigate('web-reader')">
                    <div class="flex items-center gap-3 mb-3">
                        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center shadow-md shadow-teal-500/30">
                            <i data-lucide="globe" class="w-5 h-5 text-white"></i>
                        </div>
                        <h3 class="text-lg font-black text-slate-900">Web Reader</h3>
                    </div>
                    <p class="text-sm text-slate-500 leading-relaxed">Paste any link. ClearRead simplifies the page, then discuss it with Nova.</p>
                    <div class="mt-3 flex items-center gap-1 text-xs font-bold text-teal-600 opacity-0 group-hover:opacity-100 transition-opacity">
                        Simplify a page <i data-lucide="arrow-right" class="w-3 h-3"></i>
                    </div>
                </div>
            </div>
        ` : '';

        container.innerHTML = `
            <div class="max-w-3xl mb-8">
                <h1 class="text-4xl md:text-5xl font-extrabold tracking-tight mb-4 text-slate-900">
                    Read with <span class="bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary">Confidence.</span>
                </h1>
                <p class="text-lg tracking-wide text-slate-600 leading-relaxed mb-6">
                    AI-powered reading companion that listens, corrects, and coaches — in real time.
                </p>
                ${learnerUI}
            </div>

            ${modeCards}

            <h2 id="library-section" class="text-2xl font-bold mb-6 flex items-center gap-2 text-slate-800"><i data-lucide="library"></i> Reading Library</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-8">
                ${passagesHtml}
            </div>

            <!-- Powered by Amazon Nova -->
            <div class="glass-panel rounded-2xl p-6 mt-4 mb-12 border border-slate-100">
                <h3 class="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
                    <i data-lucide="zap" class="w-4 h-4"></i> Powered by Amazon Nova
                </h3>
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="text-center p-3">
                        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center mx-auto mb-2">
                            <i data-lucide="mic" class="w-5 h-5 text-white"></i>
                        </div>
                        <p class="text-xs font-bold text-slate-700">Nova 2 Sonic</p>
                        <p class="text-[10px] text-slate-400">Speech-to-Speech</p>
                    </div>
                    <div class="text-center p-3">
                        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 flex items-center justify-center mx-auto mb-2">
                            <i data-lucide="brain" class="w-5 h-5 text-white"></i>
                        </div>
                        <p class="text-xs font-bold text-slate-700">Nova 2 Lite</p>
                        <p class="text-[10px] text-slate-400">Reasoning + Analysis</p>
                    </div>
                    <div class="text-center p-3">
                        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center mx-auto mb-2">
                            <i data-lucide="eye" class="w-5 h-5 text-white"></i>
                        </div>
                        <p class="text-xs font-bold text-slate-700">Nova Vision</p>
                        <p class="text-[10px] text-slate-400">Image Understanding</p>
                    </div>
                    <div class="text-center p-3">
                        <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center mx-auto mb-2">
                            <i data-lucide="layers" class="w-5 h-5 text-white"></i>
                        </div>
                        <p class="text-xs font-bold text-slate-700">Nova Embeddings</p>
                        <p class="text-[10px] text-slate-400">Multimodal Similarity</p>
                    </div>
                </div>
            </div>
        `;
        lucide.createIcons();
    },

    async login() {
        const id = document.getElementById('login-id').value.trim();
        if (!id) return;

        await fetchAPI('/learner', { method: 'POST', body: JSON.stringify({ learner_id: id }) });

        AppState.learnerId = id;
        localStorage.setItem('clearread_learner', id);
        document.getElementById('user-profile-badge').classList.remove('hidden');
        document.getElementById('header-learner-id').innerText = id;
        this.renderHome(document.getElementById('app-container'));
    },

    switchUser() {
        AppState.learnerId = null;
        localStorage.removeItem('clearread_learner');
        document.getElementById('user-profile-badge').classList.add('hidden');
        this.renderHome(document.getElementById('app-container'));
    },

    // Session Flow

    async startSession(passageId) {
        if (!AppState.learnerId) {
            alert("Please enter a username first.");
            return;
        }

        AppState.currentPassage = AppState.passages.find(p => p.passage_id === passageId);
        if (!AppState.currentPassage) return;

        this.navigate('session');
    },

    renderSession(container) {
        const p = AppState.currentPassage;

        // Wrap words in spans for highlighting
        const words = p.text.split(' ');
        let textHtml = words.map((w, i) => `<span id="word-${i}" class="reading-word">${w}</span>`).join(' ');

        container.innerHTML = `
            <div class="flex justify-between items-center mb-6">
                <button onclick="app.navigate('home')" class="text-slate-500 hover:text-slate-900 flex items-center gap-2 transition-colors">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i> Back
                </button>
                <div class="flex items-center gap-3 bg-white/50 px-4 py-2 rounded-full border border-slate-200 shadow-sm">
                    <i data-lucide="type" class="w-4 h-4 text-slate-500"></i>
                    <span class="text-sm font-medium text-slate-700">Dyslexic Font</span>
                    <button id="font-toggle" onclick="app.toggleFont()" class="w-12 h-6 rounded-full bg-primary relative transition-colors ml-2 shadow-inner">
                        <div class="absolute right-1 top-1 w-4 h-4 rounded-full bg-white transition-transform shadow-sm"></div>
                    </button>
                </div>
            </div>

            <div class="glass-card bg-white/80 rounded-3xl border border-slate-200 shadow-xl relative flex flex-col h-[70vh] max-h-[800px]">
                
                <!-- Text Area (Scrollable) -->
                <div id="text-scroll-container" class="reading-container flex-grow p-8 md:p-12">
                    <h2 class="text-3xl font-bold mb-8 text-center text-slate-900 tracking-wide">${p.title}</h2>
                    <div id="reading-text" class="text-2xl md:text-3xl lg:text-4xl leading-relaxed md:leading-loose text-slate-700 transition-all ${AppState.useDyslexicFont ? 'font-toggled' : ''}">
                        ${textHtml}
                    </div>
                </div>
                
                <!-- Sticky Recording Bar at Bottom -->
                <div class="recording-bar glass-panel shadow-[0_-10px_30px_rgba(0,0,0,0.05)]">
                    
                    <div id="pre-record-ui" class="flex flex-col items-center w-full animate-fade-in">
                        <button id="start-btn" onclick="app.startRecording()" class="group relative w-20 h-20 rounded-full bg-gradient-to-r from-primary to-secondary text-white flex items-center justify-center shadow-lg shadow-primary/30 transition-all hover:scale-105 hover:shadow-primary/50">
                            <i data-lucide="mic" class="w-8 h-8 group-hover:scale-110 transition-transform"></i>
                            <div class="absolute inset-0 rounded-full border-2 border-primary/20 scale-110 opacity-0 group-hover:opacity-100 group-hover:scale-125 transition-all duration-500"></div>
                        </button>
                        <p class="mt-4 text-base font-medium text-slate-600">Tap microphone to start reading</p>
                    </div>

                    <div id="active-record-ui" class="hidden flex justify-between items-center w-full px-8 animate-fade-in">
                        <div class="flex items-center gap-4">
                            <div class="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center recording-pulse">
                                <i data-lucide="mic" class="w-5 h-5 text-primary"></i>
                            </div>
                            <div>
                                <p class="text-base font-bold text-slate-900 flex items-center gap-2">
                                    Listening <span class="flex gap-1"><span class="w-1 h-1 bg-primary rounded-full animate-bounce"></span><span class="w-1 h-1 bg-primary rounded-full animate-bounce" style="animation-delay: 0.1s"></span><span class="w-1 h-1 bg-primary rounded-full animate-bounce" style="animation-delay: 0.2s"></span></span>
                                </p>
                                <p class="text-xs text-slate-500">Read the passage. Coach Nova is listening quietly!</p>
                            </div>
                        </div>
                        
                        <button id="stop-btn" onclick="app.stopRecording()" class="flex items-center gap-2 px-6 py-3 rounded-full bg-red-50 hover:bg-red-100 text-red-600 border border-red-200 font-bold transition-all hover:scale-105">
                            <i data-lucide="square" class="w-4 h-4 fill-current"></i> Stop Reading
                        </button>
                    </div>

                    <div id="processing-ui" class="hidden flex flex-col items-center w-full animate-fade-in">
                        <div class="w-12 h-12 rounded-full border-4 border-primary border-t-transparent animate-spin mb-3"></div>
                        <p class="text-base font-bold text-slate-900">Generating Feedback...</p>
                        <p class="text-xs text-slate-500">Coach Nova is writing your review</p>
                    </div>

                </div>
            </div>
        `;
        lucide.createIcons();
        this.updateFontToggleUI();
    },

    toggleFont() {
        AppState.useDyslexicFont = !AppState.useDyslexicFont;
        const txt = document.getElementById('reading-text');
        if (txt) {
            AppState.useDyslexicFont ? txt.classList.add('font-toggled') : txt.classList.remove('font-toggled');
        }
        this.updateFontToggleUI();
    },

    updateFontToggleUI() {
        const btn = document.getElementById('font-toggle');
        if (!btn) return;
        if (AppState.useDyslexicFont) {
            btn.classList.add('bg-primary');
            btn.classList.remove('bg-slate-300');
            btn.children[0].style.transform = 'translateX(0)';
        } else {
            btn.classList.remove('bg-primary');
            btn.classList.add('bg-slate-300');
            btn.children[0].style.transform = 'translateX(-24px)';
        }
    },

    // Audio Recording & WebSocket Logic

    async startRecording() {
        try {
            AppState.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        } catch (e) {
            alert("Microphone access is required for coaching.");
            return;
        }

        AppState.isRecording = true;

        // Swap UI
        document.getElementById('pre-record-ui').classList.add('hidden');
        document.getElementById('active-record-ui').classList.remove('hidden');

        // Init Audio
        AppState.audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = AppState.audioContext.createMediaStreamSource(AppState.mediaStream);
        const processor = AppState.audioContext.createScriptProcessor(4096, 1, 1);

        source.connect(processor);
        processor.connect(AppState.audioContext.destination);

        // Init WebSocket
        AppState.ws = new WebSocket(`${WS_BASE}/session/${AppState.learnerId}`);
        AppState.ws.binaryType = 'arraybuffer';

        AppState.ws.onopen = () => {
            AppState.ws.send(JSON.stringify({ type: "start_audio" }));
        };

        processor.onaudioprocess = (e) => {
            if (!AppState.isRecording || AppState.ws.readyState !== WebSocket.OPEN) return;

            const floatDat = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(floatDat.length);
            for (let i = 0; i < floatDat.length; i++) {
                let s = Math.max(-1, Math.min(1, floatDat[i]));
                pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            AppState.ws.send(pcm16.buffer);
        };

        AppState.ws.onmessage = async (event) => {
            if (typeof event.data === 'string') {
                const msg = JSON.parse(event.data);
                if (msg.type === 'word') {
                    const el = document.getElementById(`word-${msg.position}`);
                    if (el) {
                        el.classList.add('word-reading');

                        // Auto-scroll to keep word in view
                        const container = document.getElementById('text-scroll-container');
                        if (container) {
                            const wordRect = el.getBoundingClientRect();
                            const containerRect = container.getBoundingClientRect();
                            // If word is past middle of container, scroll down
                            if (wordRect.top > containerRect.top + (containerRect.height * 0.6)) {
                                container.scrollBy({ top: 100, behavior: 'smooth' });
                            }
                        }

                        setTimeout(() => {
                            el.classList.remove('word-reading');
                            el.classList.add('word-read');
                            if (msg.confidence < 0.75) el.classList.add('word-low-conf');
                        }, 500);
                    }
                } else if (msg.type === 'session_complete') {
                    this.finishSession(msg);
                }
            } else {
                this.playAudioPCM(event.data);
            }
        };
    },

    stopRecording() {
        if (!AppState.isRecording) return;
        AppState.isRecording = false;

        // Swap UI
        document.getElementById('active-record-ui').classList.add('hidden');
        document.getElementById('processing-ui').classList.remove('hidden');

        if (AppState.ws && AppState.ws.readyState === WebSocket.OPEN) {
            AppState.ws.send(JSON.stringify({ type: "stop_audio" }));
        }

        if (AppState.mediaStream) {
            AppState.mediaStream.getTracks().forEach(t => t.stop());
        }
    },

    async playAudioPCM(arrayBuffer) {
        // Nova Sonic returns raw 16-bit PCM at 24000 Hz usually
        const pcm16 = new Int16Array(arrayBuffer);
        const audioBuffer = AppState.audioContext.createBuffer(1, pcm16.length, 24000);
        const f32 = audioBuffer.getChannelData(0);
        for (let i = 0; i < pcm16.length; i++) {
            f32[i] = pcm16[i] / 32768.0;
        }

        const source = AppState.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(AppState.audioContext.destination);
        source.start();
    },

    async finishSession(wsData) {
        renderLoading();

        // Post to /api/session/complete to trigger Nova Lite analysis & Embeddings
        const fullPayload = {
            learner_id: AppState.learnerId,
            passage_id: AppState.currentPassage.passage_id,
            word_events: wsData.word_events,
            duration_seconds: wsData.duration_seconds
        };

        const result = await fetchAPI('/session/complete', {
            method: 'POST',
            body: JSON.stringify(fullPayload)
        });

        if (result) {
            AppState.sessionData = result;
            this.navigate('results', result);
        } else {
            alert("Error processing session.");
            this.navigate('home');
        }
    },

    // Results View

    renderResults(container, data) {
        if (!data) { this.navigate('home'); return; }

        const summary = data.session_summary;
        const drills = data.micro_drills || [];
        const adapted = data.adapted_text;
        const recs = data.recommendations || [];
        const errorProfile = data.error_profile || {};

        // Coach feedback from Nova Lite — supports structured or legacy format
        const coachFeedback = errorProfile.coach_feedback || null;
        const legacyMessage = errorProfile.coach_message || null;

        // Build structured feedback HTML
        let feedbackHtml = '';
        if (coachFeedback && typeof coachFeedback === 'object') {
            feedbackHtml = `
                <div class="space-y-4" id="coach-feedback-sections">
                    ${coachFeedback.praise ? `
                    <div class="flex gap-3 items-start p-4 rounded-xl bg-emerald-50 border border-emerald-100">
                        <div class="w-10 h-10 rounded-full bg-emerald-500 flex items-center justify-center shrink-0 shadow-sm">
                            <i data-lucide="star" class="w-5 h-5 text-white"></i>
                        </div>
                        <div>
                            <div class="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">What you did great!</div>
                            <p class="text-slate-700 font-medium leading-relaxed" data-feedback="praise">${coachFeedback.praise}</p>
                        </div>
                    </div>` : ''}

                    ${coachFeedback.correction ? `
                    <div class="flex gap-3 items-start p-4 rounded-xl bg-amber-50 border border-amber-100">
                        <div class="w-10 h-10 rounded-full bg-amber-500 flex items-center justify-center shrink-0 shadow-sm">
                            <i data-lucide="pencil" class="w-5 h-5 text-white"></i>
                        </div>
                        <div>
                            <div class="text-xs font-bold text-amber-600 uppercase tracking-widest mb-1">Let's work on this</div>
                            <p class="text-slate-700 font-medium leading-relaxed" data-feedback="correction">${coachFeedback.correction}</p>
                        </div>
                    </div>` : ''}

                    ${coachFeedback.tip ? `
                    <div class="flex gap-3 items-start p-4 rounded-xl bg-blue-50 border border-blue-100">
                        <div class="w-10 h-10 rounded-full bg-blue-500 flex items-center justify-center shrink-0 shadow-sm">
                            <i data-lucide="lightbulb" class="w-5 h-5 text-white"></i>
                        </div>
                        <div>
                            <div class="text-xs font-bold text-blue-600 uppercase tracking-widest mb-1">Phonics Tip</div>
                            <p class="text-slate-700 font-medium leading-relaxed" data-feedback="tip">${coachFeedback.tip}</p>
                        </div>
                    </div>` : ''}

                    ${coachFeedback.encouragement ? `
                    <div class="flex gap-3 items-start p-4 rounded-xl bg-purple-50 border border-purple-100">
                        <div class="w-10 h-10 rounded-full bg-purple-500 flex items-center justify-center shrink-0 shadow-sm">
                            <i data-lucide="heart" class="w-5 h-5 text-white"></i>
                        </div>
                        <div>
                            <div class="text-xs font-bold text-purple-600 uppercase tracking-widest mb-1">Keep going!</div>
                            <p class="text-slate-700 font-medium leading-relaxed" data-feedback="encouragement">${coachFeedback.encouragement}</p>
                        </div>
                    </div>` : ''}
                </div>
            `;
        } else {
            // Legacy fallback
            const msg = (legacyMessage || "Great effort today! I am so proud of you.").replace('Coach Nova says:', '').trim();
            feedbackHtml = `<p class="text-xl leading-relaxed text-slate-700 font-medium tracking-wide">"${msg}"</p>`;
        }

        // Build full feedback text for TTS
        const feedbackTextForTTS = coachFeedback && typeof coachFeedback === 'object'
            ? [coachFeedback.praise, coachFeedback.correction, coachFeedback.tip, coachFeedback.encouragement].filter(Boolean).join('. ... ')
            : (legacyMessage || "Great effort today!").replace('Coach Nova says:', '').trim();

        // Build word-level color map from passage text + low confidence words
        const passageText = (data.passage || {}).text || '';
        const lowConfWords = (summary.low_confidence_words || []).map(w => w.toLowerCase());
        const flaggedPatterns = summary.flagged_phoneme_patterns || [];

        let wordMapHtml = '';
        if (passageText) {
            const words = passageText.split(/\s+/);
            wordMapHtml = words.map(w => {
                const clean = w.replace(/[.,!?;:'"]/g, '').toLowerCase();
                if (lowConfWords.includes(clean)) {
                    return `<span class="word-error">${w}</span>`;
                } else if (flaggedPatterns.some(p => clean.includes(p.replace('phoneme_', '')))) {
                    return `<span class="word-warning">${w}</span>`;
                }
                return `<span class="word-correct">${w}</span>`;
            }).join(' ');
        }

        // Extract practice words
        let targetWords = [];
        if (drills.length > 0) {
            drills.forEach(d => { targetWords = targetWords.concat(d.words); });
        }
        if (lowConfWords.length > 0) {
            targetWords = targetWords.concat(lowConfWords);
        }
        if (targetWords.length === 0) targetWords = ["great", "reading", "today"];
        const uniqueWords = [...new Set(targetWords)];
        const practiceWordsEncoded = encodeURIComponent(JSON.stringify(uniqueWords));

        // Practice words section
        let practiceHtml = '';
        if (uniqueWords.length > 0 && lowConfWords.length > 0) {
            practiceHtml = `
                <div class="glass-panel p-6 rounded-2xl border border-rose-100 bg-rose-50/50 shadow-sm mb-4">
                    <p class="text-slate-600 mb-4 font-medium">Words to practice:</p>
                    <div class="flex flex-wrap gap-2 mb-4">
                        ${uniqueWords.map(w => `<span class="bg-white px-4 py-2 rounded-xl text-rose-600 font-black shadow-sm border border-rose-100">${w}</span>`).join('')}
                    </div>
                </div>`;
        }
        practiceHtml += `
            <button onclick="app.navigate('practice', '${practiceWordsEncoded}')" class="w-full py-4 text-white bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-600 hover:to-purple-700 rounded-xl font-black text-lg flex items-center justify-center gap-3 shadow-lg shadow-indigo-500/30 transition-transform transform hover:scale-105">
                <i data-lucide="mic" class="w-6 h-6"></i> Practice with Coach Nova
            </button>
        `;

        let recsHtml = recs.length === 0 ? '<p class="text-slate-500">Check back later for new stories.</p>' : '';
        recs.forEach(r => {
            recsHtml += `
                <div class="glass-panel p-4 rounded-xl flex items-center justify-between mb-3 hover:bg-slate-50 transition-colors cursor-pointer border border-transparent hover:border-emerald-500/30" onclick="app.startSession('${r.passage_id}')">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-full bg-emerald-500/10 flex items-center justify-center">
                            <i data-lucide="book" class="w-6 h-6 text-emerald-500"></i>
                        </div>
                        <div>
                            <h4 class="font-bold text-slate-800 text-lg">${r.title}</h4>
                            <p class="text-sm text-slate-500 mt-1">Perfect for your current level</p>
                        </div>
                    </div>
                    <i data-lucide="play-circle" class="w-8 h-8 text-emerald-400 opacity-50"></i>
                </div>
            `;
        });

        container.innerHTML = `
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-3xl font-extrabold text-slate-900">Session Complete!</h2>
                <div class="flex gap-3">
                    <button onclick="app.navigate('progress', '${AppState.learnerId}')" class="btn-primary text-sm px-4">My Progress</button>
                    <button onclick="app.navigate('home')" class="btn-secondary text-sm px-4 bg-white border-slate-200 text-slate-700 hover:text-slate-900 glass-panel">Done</button>
                </div>
            </div>

            <!-- Coach Feedback -->
            <div class="glass-card p-6 md:p-8 mb-8 border-primary/20 relative overflow-hidden bg-gradient-to-r from-white to-slate-50 shadow-md">
                <div class="absolute -right-10 -top-10 w-40 h-40 bg-primary/10 rounded-full blur-3xl"></div>
                
                <div class="relative z-10">
                    <div class="flex items-center justify-between mb-5">
                        <div class="flex items-center gap-4">
                            <div class="w-14 h-14 shrink-0 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 p-1 shadow-lg shadow-indigo-500/30 transform -rotate-6">
                                <div class="w-full h-full bg-white rounded-xl flex items-center justify-center">
                                    <i data-lucide="bot" class="w-7 h-7 text-primary"></i>
                                </div>
                            </div>
                            <h3 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-indigo-500 to-purple-500">Coach Nova's Review</h3>
                        </div>
                        <button onclick="app.playCoachFeedback()" class="flex items-center gap-2 text-sm font-bold text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-full transition-colors">
                            <i data-lucide="volume-2" class="w-4 h-4"></i> Read to me
                        </button>
                    </div>
                    ${feedbackHtml}
                </div>
            </div>

            ${wordMapHtml ? `
            <!-- Word-Level Analysis -->
            <div class="glass-card p-6 md:p-8 mb-8 border-slate-200 shadow-sm bg-white/80">
                <h3 class="text-xl font-black mb-4 flex items-center gap-2 text-slate-900">
                    <i data-lucide="scan-text" class="w-5 h-5 text-indigo-500"></i> Word Analysis
                </h3>
                <p class="text-xs text-slate-400 mb-4"><span class="word-correct">Green</span> = great, <span class="word-warning">Orange</span> = tricky, <span class="word-error">Red</span> = needs practice</p>
                <div class="text-lg leading-loose tracking-wide">
                    ${wordMapHtml}
                </div>
            </div>
            ` : ''}

            <!-- Stats Toggle -->
            <details class="glass-panel rounded-xl mb-8 group cursor-pointer border border-slate-200 shadow-sm">
                <summary class="p-4 flex justify-between items-center font-bold text-slate-500 hover:text-slate-800 outline-none">
                    <span class="flex items-center gap-2"><i data-lucide="line-chart" class="w-4 h-4"></i> Detailed Metrics</span>
                    <i data-lucide="chevron-down" class="w-4 h-4 group-open:rotate-180 transition-transform"></i>
                </summary>
                <div class="p-4 pt-0 border-t border-slate-100 mt-2">
                    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                        <div class="bg-white p-4 rounded-lg text-center border border-slate-100 shadow-sm">
                            <div class="text-slate-500 text-xs font-bold mb-1 uppercase tracking-widest">Speed</div>
                            <div class="text-3xl font-black text-slate-800">${Math.round(summary.words_per_minute)} <span class="text-xs text-slate-500 font-normal">WPM</span></div>
                        </div>
                        <div class="bg-white p-4 rounded-lg text-center border border-slate-100 shadow-sm">
                            <div class="text-slate-500 text-xs font-bold mb-1 uppercase tracking-widest">Accuracy</div>
                            <div class="text-3xl font-black text-slate-800">${Math.round(summary.accuracy_rate * 100)}%</div>
                        </div>
                        <div class="bg-white p-4 rounded-lg text-center border border-slate-100 shadow-sm">
                            <div class="text-slate-500 text-xs font-bold mb-1 uppercase tracking-widest">Hesitations</div>
                            <div class="text-3xl font-black text-slate-800">${summary.hesitation_count}</div>
                        </div>
                        <div class="bg-white p-4 rounded-lg text-center border border-slate-100 shadow-sm">
                            <div class="text-slate-500 text-xs font-bold mb-1 uppercase tracking-widest">Pattern</div>
                            <div class="text-sm font-bold text-pink-500 mt-2 truncate">${(summary.primary_pattern || 'None').replace('phoneme_', '')}</div>
                        </div>
                    </div>
                </div>
            </details>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pb-12">
                <div>
                    <h3 class="text-2xl font-black mb-4 flex items-center gap-2 text-slate-900">Practice Mode</h3>
                    ${practiceHtml}
                </div>
                <div>
                    <h3 class="text-2xl font-black mb-4 flex items-center gap-2 text-slate-900">Next Adventures</h3>
                    ${recsHtml}
                </div>
            </div>
        `;
        lucide.createIcons();

        // Store feedback text for TTS and auto-play
        this._feedbackTTS = feedbackTextForTTS;
        setTimeout(() => this.playCoachFeedback(), 1200);
    },

    _feedbackTTS: '',

    playCoachFeedback() {
        const text = this._feedbackTTS || '';
        if (!text || !window.speechSynthesis) return;
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.85;
        utterance.pitch = 1.1;

        const voices = speechSynthesis.getVoices();
        const friendlyVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Tessa') || v.name.includes('Google US English'));
        if (friendlyVoice) utterance.voice = friendlyVoice;

        speechSynthesis.speak(utterance);
    },

    playCoachMessage(text) {
        if (!window.speechSynthesis) return;
        speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1.1;
        const voices = speechSynthesis.getVoices();
        const friendlyVoice = voices.find(v => v.name.includes('Samantha') || v.name.includes('Tessa') || v.name.includes('Google US English'));
        if (friendlyVoice) utterance.voice = friendlyVoice;
        speechSynthesis.speak(utterance);
    },

    // Progress View (Skill Tree)

    async renderProgress(container, learnerId) {
        renderLoading();
        const data = await fetchAPI(`/learner/${learnerId}/progress`);
        if (!data) { this.navigate('home'); return; }

        let skillsHtml = '';

        // Map clinical terms to kid-friendly skills
        const skillMap = {
            'phonological_decoding': { name: 'Sounding Out Words', icon: 'mic-2', color: 'bg-emerald-500' },
            'visual_tracking': { name: 'Keeping Your Place', icon: 'eye', color: 'bg-blue-500' },
            'working_memory': { name: 'Remembering the Story', icon: 'brain', color: 'bg-purple-500' },
            'fluency': { name: 'Reading Smoothly', icon: 'zap', color: 'bg-amber-500' }
        };

        Object.keys(skillMap).forEach(cat => {
            const e = data.error_trends[cat] || { severity: 5 };
            const mapping = skillMap[cat];

            // Convert severity (1-10) to progress level (1-10) - lower severity is better
            const progressLevel = Math.max(1, 10 - e.severity);
            const progressPercent = progressLevel * 10;

            skillsHtml += `
                <div class="mb-5 glass-panel p-4 rounded-xl border border-slate-200 bg-white/50 shadow-sm">
                    <div class="flex justify-between items-center mb-3">
                        <div class="flex items-center gap-3">
                            <div class="p-2 bg-slate-50 border border-slate-100 rounded-lg"><i data-lucide="${mapping.icon}" class="w-5 h-5 text-slate-500"></i></div>
                            <span class="font-bold text-slate-800 text-lg">${mapping.name}</span>
                        </div>
                        <span class="text-xs font-bold px-3 py-1 bg-white shadow-sm rounded-full text-slate-600 border border-slate-200">Level ${Math.round(progressLevel)}</span>
                    </div>
                    <div class="w-full bg-slate-100 rounded-full h-3 border border-slate-200 p-0.5">
                        <div class="${mapping.color} h-full rounded-full transition-all duration-1000 ease-out shadow-sm" style="width: ${progressPercent}%"></div>
                    </div>
                </div>
            `;
        });

        let historyHtml = '';
        data.recent_sessions.slice().reverse().forEach(s => {
            historyHtml += `
                <div class="flex items-center justify-between p-4 glass-panel rounded-xl mb-3 border border-slate-200 hover:border-slate-300 transition-colors cursor-pointer shadow-sm bg-white/50">
                    <div class="flex items-center gap-4">
                        <div class="w-10 h-10 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center">
                            <i data-lucide="award" class="w-5 h-5 text-indigo-500"></i>
                        </div>
                        <div>
                            <div class="text-base font-bold text-slate-800">${s.date}</div>
                            <div class="text-xs text-slate-500">Adventure completed</div>
                        </div>
                    </div>
                    <div class="text-right">
                        <div class="text-lg font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-500 to-cyan-500">${Math.round(s.words_per_minute)} <span class="text-xs font-medium text-slate-500">WPM</span></div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = `
            <div class="flex justify-between items-center mb-10">
                <div class="flex items-center gap-4">
                    <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 p-1 shadow-md transform -rotate-3">
                        <div class="w-full h-full bg-white rounded-xl flex items-center justify-center">
                            <i data-lucide="user" class="w-8 h-8 text-primary"></i>
                        </div>
                    </div>
                    <div>
                        <h2 class="text-4xl font-black text-slate-900 tracking-tight">Your Skill Tree</h2>
                        <p class="text-slate-500 font-medium mt-1">Leveling up as ${learnerId}</p>
                    </div>
                </div>
                <button onclick="app.navigate('home')" class="btn-secondary text-sm px-6 font-bold bg-white text-slate-700 border-slate-200 hover:text-slate-900 glass-panel shadow-sm">Back to Library</button>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
                
                <!-- WPM & Accuracy Charts -->
                <div class="glass-card p-6 md:p-8 border-slate-200 shadow-sm bg-white/80">
                    <h3 class="text-2xl font-black mb-6 flex items-center gap-3 text-slate-900"><i data-lucide="trending-up" class="text-indigo-500"></i> Reading Speed</h3>
                    <canvas id="wpm-chart" height="200"></canvas>
                </div>

                <div class="glass-card p-6 md:p-8 border-slate-200 shadow-sm bg-white/80">
                    <h3 class="text-2xl font-black mb-6 flex items-center gap-3 text-slate-900"><i data-lucide="target" class="text-emerald-500"></i> Accuracy</h3>
                    <canvas id="accuracy-chart" height="200"></canvas>
                </div>

                <!-- Skill Tree -->
                <div class="glass-card p-6 md:p-8 border-slate-200 shadow-sm bg-white/80">
                    <h3 class="text-2xl font-black mb-6 flex items-center gap-3 text-slate-900"><i data-lucide="stars" class="text-amber-500"></i> Skills</h3>
                    ${skillsHtml}
                </div>

                <!-- History -->
                <div class="glass-card p-6 md:p-8 border-slate-200 shadow-sm bg-white/80">
                    <h3 class="text-2xl font-black mb-6 flex items-center gap-3 text-slate-900"><i data-lucide="clock" class="text-slate-500"></i> Session History</h3>
                    <div class="max-h-[400px] overflow-y-auto pr-2">
                        ${historyHtml}
                    </div>
                </div>
            </div>
        `;
        lucide.createIcons();

        // Render Chart.js charts
        this._renderProgressCharts(data);
    },

    _renderProgressCharts(data) {
        if (typeof Chart === 'undefined') return;

        const wpmData = data.wpm_trend || [];
        const accData = data.accuracy_trend || [];

        const labels = wpmData.map((d, i) => d.date || `Session ${i + 1}`);

        // WPM Chart
        const wpmCtx = document.getElementById('wpm-chart');
        if (wpmCtx) {
            new Chart(wpmCtx, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Words Per Minute',
                        data: wpmData.map(d => d.value),
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#6366f1',
                        pointRadius: 5,
                        pointHoverRadius: 8,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
                        x: { grid: { display: false } }
                    },
                    animation: { duration: 1500, easing: 'easeOutQuart' }
                }
            });
        }

        // Accuracy Chart
        const accCtx = document.getElementById('accuracy-chart');
        if (accCtx) {
            new Chart(accCtx, {
                type: 'line',
                data: {
                    labels: accData.map((d, i) => d.date || `Session ${i + 1}`),
                    datasets: [{
                        label: 'Accuracy %',
                        data: accData.map(d => d.value),
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: '#10b981',
                        pointRadius: 5,
                        pointHoverRadius: 8,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, max: 100, grid: { color: 'rgba(0,0,0,0.05)' } },
                        x: { grid: { display: false } }
                    },
                    animation: { duration: 1500, easing: 'easeOutQuart' }
                }
            });
        }
    },

    // Interactive Practice Mode
    renderPractice(container, payload) {
        const interactiveView = document.getElementById('interactive-view');
        if (!interactiveView) { this.navigate('home'); return; }

        // Parse words to practice (from results page) or use general mode
        let practiceWords = [];
        try {
            if (payload) practiceWords = JSON.parse(decodeURIComponent(payload));
        } catch (e) { }

        const wordsContext = practiceWords.length > 0
            ? `Focus on these words the student struggled with: ${practiceWords.join(', ')}.`
            : '';

        interactiveView.classList.remove('hidden');
        const imageHtml = this._currentPracticeImage ? `
            <div class="hidden md:flex flex-col items-center justify-center p-6 w-full max-w-md bg-white/5 backdrop-blur-md rounded-3xl border border-white/10 shadow-2xl">
                <img src="${this._currentPracticeImage}" class="rounded-2xl border-4 border-indigo-500/30 object-contain max-h-[60vh] shadow-2xl shadow-indigo-500/20" alt="Analyzed Photo" />
            </div>
        ` : '';

        interactiveView.innerHTML = `
            <div class="absolute inset-0 bg-gradient-to-b from-slate-900 via-indigo-950 to-slate-900"></div>
            
            <!-- Header bar -->
            <div class="absolute top-0 left-0 right-0 flex items-center justify-between px-6 py-4 z-20">
                <button onclick="app.exitPractice()" class="bg-white/10 hover:bg-white/20 text-white rounded-full px-5 py-2.5 backdrop-blur-md transition-colors flex items-center gap-2 text-sm font-bold">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i> Back
                </button>
                <div class="text-white/60 text-sm font-medium" id="practice-status">Connecting...</div>
            </div>

            <!-- Central Content Area -->
            <div class="relative z-10 flex flex-col md:flex-row items-center justify-center h-full w-full max-w-7xl mx-auto pt-16 gap-8 px-6">
                
                <!-- Chat & Avatar Area -->
                <div class="flex flex-col items-center justify-center h-full flex-grow w-full ${this._currentPracticeImage ? 'max-w-xl' : 'max-w-3xl'}">
                    <div id="nova-avatar" class="w-24 h-24 md:w-32 md:h-32 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-2xl shadow-indigo-500/40 mb-4 transition-transform shrink-0">
                        <i data-lucide="bot" class="w-12 h-12 md:w-16 md:h-16 text-white"></i>
                    </div>
                    <div id="nova-pulse" class="absolute w-24 h-24 md:w-32 md:h-32 rounded-full border-2 border-indigo-400/30 animate-ping" style="animation-duration: 2s;"></div>

                    <h2 class="text-2xl font-black text-white mb-2">Coach Nova</h2>
                    <p class="text-indigo-300 text-sm mb-6 font-medium">Say something or wait for Coach Nova to speak!</p>

                    <!-- Live Transcript (Expanded) -->
                    <div id="practice-transcript" class="w-full h-full max-h-[50vh] overflow-y-auto space-y-4 mb-8 bg-black/20 rounded-3xl p-6 border border-white/5 shadow-inner">
                        <!-- Transcript bubbles added here dynamically -->
                    </div>

                    <!-- Mic Control -->
                    <div class="flex items-center gap-6 mt-auto pb-8">
                        <button id="practice-mic-btn" onclick="app.togglePracticeMic()" class="w-16 h-16 rounded-full bg-white text-slate-900 flex items-center justify-center shadow-lg shadow-white/20 hover:scale-110 transition-transform shrink-0">
                            <i data-lucide="mic" class="w-7 h-7"></i>
                        </button>
                        <button onclick="app.exitPractice()" class="px-6 py-3 rounded-full bg-red-500/20 text-red-300 border border-red-500/30 font-bold text-sm hover:bg-red-500/30 transition-colors">
                            End Practice
                        </button>
                    </div>
                </div>

                ${imageHtml}
            </div>
        `;
        lucide.createIcons();
        this._startPracticeSession(wordsContext, payload);
    },

    _practiceWs: null,
    _practiceRecording: false,
    _practiceAudioCtx: null,
    _practiceStream: null,
    _audioQueue: [],
    _isPlayingAudio: false,

    async _startPracticeSession(wordsContext, payload) {
        const statusEl = document.getElementById('practice-status');
        statusEl.innerText = 'Connecting to Coach Nova...';

        try {
            this._practiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        } catch (e) { }

        // Connect WebSocket
        this._practiceWs = new WebSocket(`${WS_BASE}/interactive/${AppState.learnerId}`);
        this._practiceWs.binaryType = 'arraybuffer';

        this._practiceWs.onopen = () => {
            statusEl.innerText = 'Connected — listening';
            let contextToSend = wordsContext;

            // Check if payload is a JSON object with 'vision_context'
            try {
                if (payload) {
                    const parsed = JSON.parse(decodeURIComponent(payload));
                    if (parsed && parsed.type === 'vision_context') {
                        contextToSend = `The student just took a picture of this: ${parsed.scene}. Text visible in picture: ${parsed.text}. A generated passage about it: ${parsed.passage}`;
                    }
                }
            } catch (e) { }

            this._practiceWs.send(JSON.stringify({
                type: 'start_audio',
                words_context: contextToSend
            }));
            // Auto-start mic
            this._startPracticeMic();
        };

        this._practiceWs.onmessage = async (event) => {
            if (typeof event.data === 'string') {
                const msg = JSON.parse(event.data);
                if (msg.type === 'transcript') {
                    this._addTranscriptBubble(msg.role, msg.text);
                } else if (msg.type === 'status') {
                    statusEl.innerText = msg.message;
                }
            } else {
                // Binary audio from Coach Nova — queue and play
                this._queueAudio(event.data);
            }
        };

        this._practiceWs.onclose = () => {
            statusEl.innerText = 'Disconnected';
        };
    },

    _addTranscriptBubble(role, text) {
        const container = document.getElementById('practice-transcript');
        if (!container) return;
        const isUser = role === 'USER';
        const bubble = document.createElement('div');
        bubble.className = `px-4 py-3 rounded-2xl text-sm font-medium max-w-[80%] animate-fade-in ${isUser
            ? 'bg-white/10 text-white/90 ml-auto'
            : 'bg-indigo-500/30 text-indigo-100 mr-auto border border-indigo-400/20'
            }`;
        bubble.innerText = text;
        container.appendChild(bubble);
        container.scrollTop = container.scrollHeight;

        // Pulse avatar when Nova speaks
        if (!isUser) {
            const avatar = document.getElementById('nova-avatar');
            if (avatar) {
                avatar.classList.add('scale-110');
                setTimeout(() => avatar.classList.remove('scale-110'), 1000);
            }
        }
    },

    async _startPracticeMic() {
        try {
            this._practiceStream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true }
            });
        } catch (e) {
            document.getElementById('practice-status').innerText = 'Microphone access denied';
            return;
        }

        this._practiceRecording = true;
        const btn = document.getElementById('practice-mic-btn');
        if (btn) btn.classList.add('bg-red-500', 'text-white');

        if (!this._practiceAudioCtx || this._practiceAudioCtx.state === 'closed') {
            this._practiceAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        }

        const source = this._practiceAudioCtx.createMediaStreamSource(this._practiceStream);
        const processor = this._practiceAudioCtx.createScriptProcessor(4096, 1, 1);
        source.connect(processor);
        processor.connect(this._practiceAudioCtx.destination);

        this._practiceProcessor = processor;
        this._practiceSource = source;

        processor.onaudioprocess = (e) => {
            if (!this._practiceRecording || !this._practiceWs || this._practiceWs.readyState !== WebSocket.OPEN) return;
            const floatDat = e.inputBuffer.getChannelData(0);
            const pcm16 = new Int16Array(floatDat.length);
            for (let i = 0; i < floatDat.length; i++) {
                let s = Math.max(-1, Math.min(1, floatDat[i]));
                pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            this._practiceWs.send(pcm16.buffer);
        };
    },

    _stopPracticeMic() {
        this._practiceRecording = false;
        if (this._practiceStream) {
            this._practiceStream.getTracks().forEach(t => t.stop());
            this._practiceStream = null;
        }
        const btn = document.getElementById('practice-mic-btn');
        if (btn) {
            btn.classList.remove('bg-red-500', 'text-white');
        }
    },

    togglePracticeMic() {
        if (this._practiceRecording) {
            this._stopPracticeMic();
        } else {
            this._startPracticeMic();
        }
    },

    async _queueAudio(arrayBuffer) {
        this._audioQueue.push(arrayBuffer);
        if (!this._isPlayingAudio) this._playNextAudio();
    },

    async _playNextAudio() {
        if (this._audioQueue.length === 0) {
            this._isPlayingAudio = false;
            return;
        }
        this._isPlayingAudio = true;
        const buf = this._audioQueue.shift();

        try {
            const playCtx = new (window.AudioContext || window.webkitAudioContext)();
            const pcm16 = new Int16Array(buf);
            const audioBuffer = playCtx.createBuffer(1, pcm16.length, 24000);
            const f32 = audioBuffer.getChannelData(0);
            for (let i = 0; i < pcm16.length; i++) {
                f32[i] = pcm16[i] / 32768.0;
            }
            const source = playCtx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(playCtx.destination);
            source.onended = () => this._playNextAudio();
            source.start();
        } catch (e) {
            this._playNextAudio();
        }
    },

    exitPractice() {
        this._stopPracticeMic();
        if (this._practiceWs) {
            try {
                this._practiceWs.send(JSON.stringify({ type: "stop_audio" }));
                this._practiceWs.close();
            } catch (e) { }
            this._practiceWs = null;
        }
        this._audioQueue = [];
        this._isPlayingAudio = false;
        this._currentPracticeImage = null;

        const interactiveView = document.getElementById('interactive-view');
        if (interactiveView) {
            interactiveView.classList.add('hidden');
            interactiveView.innerHTML = '';
        }
        // Navigate back
        this.navigate('home');
    },

    // Picture Reading (Nova Vision)

    renderPictureReading(container) {
        container.innerHTML = `
            <div class="max-w-2xl mx-auto">
                <div class="flex justify-between items-center mb-8">
                    <div class="flex items-center gap-4">
                        <div class="w-14 h-14 rounded-2xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center shadow-lg">
                            <i data-lucide="camera" class="w-7 h-7 text-white"></i>
                        </div>
                        <div>
                            <h2 class="text-3xl font-black text-slate-900">Picture Reading</h2>
                            <p class="text-sm text-slate-500">Nova Vision → Personalized Passage</p>
                        </div>
                    </div>
                    <button onclick="app.navigate('home')" class="px-4 py-2 text-sm font-bold bg-white border-2 border-slate-200 text-slate-700 rounded-xl hover:border-slate-400 transition-colors">Back</button>
                </div>

                <div id="pr-upload-area" class="glass-card p-8 border-amber-100 text-center cursor-pointer hover:border-amber-300 transition-all"
                     onclick="document.getElementById('pr-file-input').click()">
                    <div class="w-20 h-20 rounded-full bg-amber-50 flex items-center justify-center mx-auto mb-4 border-2 border-dashed border-amber-300">
                        <i data-lucide="image-plus" class="w-10 h-10 text-amber-400"></i>
                    </div>
                    <h3 class="text-xl font-bold text-slate-700 mb-2">Upload or Take a Photo</h3>
                    <p class="text-sm text-slate-400 mb-4">A book page, a sign, a cereal box — anything with text!</p>
                    <p class="text-xs text-slate-300">JPG, PNG, WebP supported</p>
                    <input type="file" id="pr-file-input" accept="image/*" capture="environment" class="hidden" onchange="app._handlePictureUpload(event)">
                </div>

                <div id="pr-preview" class="hidden mt-6"></div>
                <div id="pr-results" class="hidden mt-6"></div>
            </div>
        `;
        lucide.createIcons();
    },

    async _handlePictureUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Show preview
        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64Full = e.target.result;
            const base64Data = base64Full.split(',')[1];
            const mediaType = file.type || 'image/jpeg';

            // Show image preview + loading
            document.getElementById('pr-upload-area').classList.add('hidden');
            const preview = document.getElementById('pr-preview');
            preview.classList.remove('hidden');
            preview.innerHTML = `
                <div class="glass-card p-4 border-amber-100">
                    <img src="${base64Full}" class="rounded-xl w-full max-h-64 object-cover mb-4" alt="Uploaded photo">
                    <div class="flex items-center gap-3 justify-center text-amber-600">
                        <div class="animate-spin w-5 h-5 border-3 border-amber-200 border-t-amber-500 rounded-full"></div>
                        <span class="font-bold text-sm">Nova Vision is analyzing your photo...</span>
                    </div>
                </div>
            `;

            try {
                const result = await fetchAPI('/vision/analyze', {
                    method: 'POST',
                    body: JSON.stringify({
                        learner_id: AppState.learnerId || 'guest',
                        image_base64: base64Data,
                        media_type: mediaType
                    })
                });
                this._showPictureResults(result, base64Full);
            } catch (err) {
                preview.innerHTML += `<p class="text-red-500 mt-4 text-center">Analysis failed. <button onclick="app.renderPictureReading(document.getElementById('app-container'))" class="underline">Try again</button></p>`;
            }
        };
        reader.readAsDataURL(file);
    },

    _showPictureResults(result, imgSrc) {
        const resultsDiv = document.getElementById('pr-results');
        if (!resultsDiv) return;

        // Update preview to remove spinner
        const preview = document.getElementById('pr-preview');
        if (preview) {
            preview.innerHTML = `
                <div class="glass-card p-4 border-amber-100">
                    <img src="${imgSrc}" class="rounded-xl w-full max-h-48 object-cover" alt="Your photo">
                </div>
            `;
        }

        const vocabHtml = (result.vocabulary_words || []).map(w =>
            `<span class="inline-block px-3 py-1 text-sm font-bold rounded-full bg-amber-100 text-amber-700 border border-amber-200">${w}</span>`
        ).join(' ');

        resultsDiv.classList.remove('hidden');
        resultsDiv.innerHTML = `
            <!-- Scene Description -->
            <div class="glass-card p-5 border-slate-100 mb-4">
                <div class="flex items-center gap-2 mb-2">
                    <i data-lucide="eye" class="w-4 h-4 text-amber-500"></i>
                    <span class="text-xs font-bold text-slate-400 uppercase">What Nova Sees</span>
                </div>
                <p class="text-slate-700 leading-relaxed">${result.scene_description || 'Unable to describe the scene.'}</p>
            </div>

            ${result.detected_text ? `
            <div class="glass-card p-5 border-slate-100 mb-4">
                <div class="flex items-center gap-2 mb-2">
                    <i data-lucide="scan-text" class="w-4 h-4 text-blue-500"></i>
                    <span class="text-xs font-bold text-slate-400 uppercase">Text Detected (OCR)</span>
                </div>
                <p class="text-slate-700 font-mono text-sm bg-slate-50 p-3 rounded-lg">${result.detected_text}</p>
            </div>` : ''}

            <!-- Generated Passage -->
            <div class="glass-card p-6 border-emerald-100 mb-4">
                <div class="flex items-center gap-2 mb-3">
                    <i data-lucide="book-open" class="w-4 h-4 text-emerald-500"></i>
                    <span class="text-xs font-bold text-slate-400 uppercase">Your Personalized Reading Passage</span>
                </div>
                <p class="text-lg text-slate-800 leading-relaxed font-medium" id="pr-passage-text">${result.generated_passage}</p>
                ${vocabHtml ? `<div class="mt-4 flex flex-wrap gap-2">${vocabHtml}</div>` : ''}
            </div>

            <!-- Actions -->
            <div class="flex gap-4">
                <button onclick="app._startPictureSession()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3.5 px-6 rounded-2xl shadow-lg shadow-indigo-200 transition-all active:scale-95 flex items-center justify-center gap-2">
                    <i data-lucide="mic" class="w-5 h-5"></i>
                    Read This Passage
                </button>
                <button onclick="app._startPicturePractice()" class="w-full bg-white text-indigo-600 border-2 border-indigo-100 font-bold py-3.5 px-6 rounded-2xl shadow-sm hover:shadow hover:border-indigo-200 transition-all active:scale-95 flex items-center justify-center gap-2">
                    <i data-lucide="bot" class="w-5 h-5"></i>
                    Discuss with Coach Nova
                </button>
                
                <button onclick="app._resetPictureReading()" class="w-full bg-slate-100 text-slate-500 font-bold py-3.5 px-6 rounded-2xl hover:bg-slate-200 transition-colors flex items-center justify-center gap-2">
                    <i data-lucide="camera" class="w-5 h-5"></i>
                    Take a New Photo
                </button>
            </div>
        `;
        lucide.createIcons();

        // Store the generated passage for potential reading session
        this._picturePassage = result;
        this._lastPictureImgSrc = imgSrc;
    },

    _startPictureSession() {
        if (!this._picturePassage || !this._picturePassage.generated_passage) return;

        AppState.currentPassage = {
            passage_id: 'vision_generated_' + Date.now(),
            title: 'Picture Reading',
            text: this._picturePassage.generated_passage,
            difficulty_band: this._picturePassage.difficulty_band || 'grade_1'
        };

        this.navigate('session');
    },

    _startPicturePractice() {
        if (!this._picturePassage) return;

        // Set the current image so renderPractice can display it side-by-side
        if (this._lastPictureImgSrc) {
            this._currentPracticeImage = this._lastPictureImgSrc;
        }

        // Pass the context of the image to the practice session
        const contextData = {
            type: 'vision_context',
            scene: this._picturePassage.scene_description || '',
            text: this._picturePassage.detected_text || '',
            passage: this._picturePassage.generated_passage || ''
        };

        this.renderPractice(document.getElementById('app-container'), encodeURIComponent(JSON.stringify(contextData)));
    },

    _resetPictureReading() {
        this._picturePassage = null;
        this._lastPictureImgSrc = null;
        this._currentPracticeImage = null;
        this.renderPictureReading(document.getElementById('app-container'));
    },

// ═══════════════════════════════════════════════════════════════════════
// Web Reader — URL Simplification + Inline Sonic Discussion
// ═══════════════════════════════════════════════════════════════════════

_webReaderData: null,
    _webReaderWs: null,
        _webReaderRecording: false,
            _webReaderAudioCtx: null,
                _webReaderPlayCtx: null,
                    _webReaderStream: null,
                        _webReaderAudioQueue: [],
                            _webReaderPlayingAudio: false,
                                _wrSonicOpen: false,
                                    _webReaderCustom: {
    fontSize: 20,
        letterSpacing: 2,
            wordSpacing: 4,
                lineHeight: 2.0,
                    theme: 'cream'
},

renderWebReader(container) {
    container.innerHTML = `
            <div class="flex justify-between items-center mb-6">
                <div class="flex items-center gap-3">
                    <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-600 flex items-center justify-center shadow-md">
                        <i data-lucide="globe" class="w-5 h-5 text-white"></i>
                    </div>
                    <div>
                        <h2 class="text-2xl font-black text-slate-900">Web Reader</h2>
                        <p class="text-xs text-slate-400">Paste a link &rarr; Dyslexia-friendly page</p>
                    </div>
                </div>
                <button onclick="app.navigate('home')" class="px-4 py-2 text-sm font-bold bg-white border-2 border-slate-200 text-slate-700 rounded-xl hover:border-slate-400 transition-colors">Back</button>
            </div>

            <!-- URL Input -->
            <div id="wr-input-area" class="glass-card p-5 border-teal-100 mb-6">
                <div class="flex gap-3">
                    <input type="url" id="wr-url-input" placeholder="Paste a link — e.g. https://en.wikipedia.org/wiki/Butterfly"
                           class="flex-grow bg-white border-2 border-slate-200 rounded-xl px-4 py-3 focus:outline-none focus:border-teal-400 text-sm text-slate-900 shadow-sm"
                           onkeydown="if(event.key==='Enter') app._simplifyUrl()">
                    <button id="wr-simplify-btn" onclick="app._simplifyUrl()" class="bg-teal-600 hover:bg-teal-700 text-white px-6 py-3 rounded-xl font-bold transition-colors flex items-center gap-2 whitespace-nowrap">
                        <i data-lucide="wand-2" class="w-4 h-4"></i> Simplify
                    </button>
                </div>
            </div>

            <!-- Loading -->
            <div id="wr-loading" class="hidden glass-card p-8 text-center border-teal-100">
                <div class="w-12 h-12 rounded-full border-4 border-teal-200 border-t-teal-500 animate-spin mx-auto mb-4"></div>
                <p class="text-sm font-bold text-teal-600">Fetching and simplifying the page...</p>
                <p class="text-xs text-slate-400 mt-1">Nova Lite is rewriting the content for easier reading</p>
            </div>

            <!-- Results (2-column: content left, sonic right) -->
            <div id="wr-results" class="hidden"></div>
        `;
    lucide.createIcons();
},

    async _simplifyUrl() {
    const input = document.getElementById('wr-url-input');
    let url = (input ? input.value : '').trim();
    if (!url) return;
    if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;

    document.getElementById('wr-input-area').classList.add('hidden');
    document.getElementById('wr-loading').classList.remove('hidden');

    const result = await fetchAPI('/web/simplify', {
        method: 'POST',
        body: JSON.stringify({ url: url, learner_id: AppState.learnerId || 'guest' })
    });

    document.getElementById('wr-loading').classList.add('hidden');

    if (!result || result.error) {
        document.getElementById('wr-input-area').classList.remove('hidden');
        alert(result ? result.error : 'Failed to simplify the page. Please try a different URL.');
        return;
    }

    this._webReaderData = result;
    this._renderSimplifiedPage(result);
},

_renderSimplifiedPage(data) {
    const resultsDiv = document.getElementById('wr-results');
    if (!resultsDiv) return;

    const keyPointsHtml = (data.key_points || []).map(p =>
        `<li class="flex items-start gap-2"><i data-lucide="check-circle" class="w-4 h-4 text-teal-500 mt-0.5 shrink-0"></i><span>${p}</span></li>`
    ).join('');

    const vocabHtml = (data.vocabulary_words || []).map(v => {
        const word = typeof v === 'string' ? v : v.word;
        const def = typeof v === 'string' ? '' : (v.definition || '');
        return `<div class="inline-block px-2 py-1 mr-1.5 mb-1.5 text-xs font-bold rounded-md bg-teal-50 text-teal-700 border border-teal-200" title="${def}">${word}${def ? ' — ' + def : ''}</div>`;
    }).join('');

    const themes = {
        cream: { bg: '#fdf6e3', text: '#3b3225', name: 'Cream' },
        light: { bg: '#ffffff', text: '#1e293b', name: 'White' },
        blue: { bg: '#e0f0ff', text: '#1a365d', name: 'Blue Tint' },
        dark: { bg: '#1e293b', text: '#e2e8f0', name: 'Dark' },
        green: { bg: '#ecfdf5', text: '#1a3a2a', name: 'Green Tint' }
    };

    let themeButtonsHtml = '';
    for (const [key, val] of Object.entries(themes)) {
        const selected = key === this._webReaderCustom.theme ? 'ring-2 ring-teal-500 ring-offset-2' : '';
        themeButtonsHtml += `<button onclick="app._setWrTheme('${key}')" class="w-7 h-7 rounded-full border-2 border-slate-200 ${selected}" style="background:${val.bg}" title="${val.name}"></button>`;
    }

    const currentTheme = themes[this._webReaderCustom.theme] || themes.cream;

    resultsDiv.classList.remove('hidden');
    resultsDiv.innerHTML = `
            <!-- Top Bar: Title + Controls -->
            <div class="flex items-center justify-between glass-card p-3 border-slate-100 mb-4">
                <div class="flex items-center gap-2 min-w-0">
                    <i data-lucide="file-text" class="w-4 h-4 text-teal-500 shrink-0"></i>
                    <h3 class="text-sm font-black text-slate-900 truncate">${data.title || 'Web Page'}</h3>
                    <span class="text-xs text-slate-300 shrink-0">&middot; ~${data.original_word_count || 0} words</span>
                </div>
                <div class="flex gap-2 shrink-0">
                    <a href="${data.url}" target="_blank" class="text-xs text-teal-500 hover:underline font-medium">Original</a>
                    <span class="text-slate-300">|</span>
                    <button onclick="app._resetWebReader()" class="text-xs text-slate-500 hover:text-slate-700 font-medium">New page</button>
                </div>
            </div>

            <!-- 2-Column Layout: Content + Sonic Side Panel -->
            <div class="flex gap-5 items-start">
                <!-- Left: Scrollable Content Column -->
                <div class="flex-grow min-w-0">
                    <!-- Customization (compact row) -->
                    <details class="glass-card rounded-xl mb-4 border border-slate-200">
                        <summary class="p-3 flex justify-between items-center font-bold text-slate-600 hover:text-slate-800 cursor-pointer select-none text-xs">
                            <span class="flex items-center gap-2"><i data-lucide="settings" class="w-3.5 h-3.5"></i> Reading Preferences</span>
                            <i data-lucide="chevron-down" class="w-3.5 h-3.5"></i>
                        </summary>
                        <div class="px-3 pb-3">
                            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
                                <div>
                                    <label class="text-xs font-bold text-slate-500 block mb-1">Font</label>
                                    <div class="flex items-center gap-1">
                                        <button onclick="app._adjustWr('fontSize', -2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">-</button>
                                        <span id="wr-fontSize-val" class="text-xs font-bold text-slate-700 w-6 text-center">${this._webReaderCustom.fontSize}</span>
                                        <button onclick="app._adjustWr('fontSize', 2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">+</button>
                                    </div>
                                </div>
                                <div>
                                    <label class="text-xs font-bold text-slate-500 block mb-1">Letter</label>
                                    <div class="flex items-center gap-1">
                                        <button onclick="app._adjustWr('letterSpacing', -1)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">-</button>
                                        <span id="wr-letterSpacing-val" class="text-xs font-bold text-slate-700 w-6 text-center">${this._webReaderCustom.letterSpacing}</span>
                                        <button onclick="app._adjustWr('letterSpacing', 1)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">+</button>
                                    </div>
                                </div>
                                <div>
                                    <label class="text-xs font-bold text-slate-500 block mb-1">Word</label>
                                    <div class="flex items-center gap-1">
                                        <button onclick="app._adjustWr('wordSpacing', -2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">-</button>
                                        <span id="wr-wordSpacing-val" class="text-xs font-bold text-slate-700 w-6 text-center">${this._webReaderCustom.wordSpacing}</span>
                                        <button onclick="app._adjustWr('wordSpacing', 2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">+</button>
                                    </div>
                                </div>
                                <div>
                                    <label class="text-xs font-bold text-slate-500 block mb-1">Line</label>
                                    <div class="flex items-center gap-1">
                                        <button onclick="app._adjustWr('lineHeight', -0.2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">-</button>
                                        <span id="wr-lineHeight-val" class="text-xs font-bold text-slate-700 w-6 text-center">${this._webReaderCustom.lineHeight.toFixed(1)}</span>
                                        <button onclick="app._adjustWr('lineHeight', 0.2)" class="w-7 h-7 rounded bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-xs font-bold">+</button>
                                    </div>
                                </div>
                            </div>
                            <div>
                                <label class="text-xs font-bold text-slate-500 block mb-1">Theme</label>
                                <div class="flex items-center gap-2">${themeButtonsHtml}</div>
                            </div>
                        </div>
                    </details>

                    <!-- Simplified Page Content -->
                    <div id="wr-content-box" class="wr-page rounded-2xl p-6 md:p-8 mb-4 border-2 border-slate-200 shadow-sm transition-all duration-300" style="
                        background: ${currentTheme.bg};
                        color: ${currentTheme.text};
                        font-size: ${this._webReaderCustom.fontSize}px;
                        letter-spacing: ${this._webReaderCustom.letterSpacing}px;
                        word-spacing: ${this._webReaderCustom.wordSpacing}px;
                        line-height: ${this._webReaderCustom.lineHeight};
                        font-family: 'OpenDyslexic', 'Comic Sans MS', 'Verdana', sans-serif;
                    ">
                        ${data.simplified_html || '<p>Content could not be simplified.</p>'}
                    </div>

                    ${keyPointsHtml ? `
                    <div class="glass-card p-4 border-slate-100 mb-4">
                        <div class="flex items-center gap-2 mb-2">
                            <i data-lucide="list-checks" class="w-4 h-4 text-teal-500"></i>
                            <span class="text-xs font-bold text-slate-400 uppercase">Key Points</span>
                        </div>
                        <ul class="space-y-1.5 text-sm text-slate-700">${keyPointsHtml}</ul>
                    </div>` : ''}

                    ${vocabHtml ? `
                    <div class="glass-card p-4 border-slate-100 mb-4">
                        <div class="flex items-center gap-2 mb-2">
                            <i data-lucide="book-a" class="w-4 h-4 text-amber-500"></i>
                            <span class="text-xs font-bold text-slate-400 uppercase">Vocabulary</span>
                        </div>
                        <div>${vocabHtml}</div>
                    </div>` : ''}

                    <div class="glass-card p-4 border-slate-100 mb-6">
                        <div class="flex items-center gap-2 mb-1">
                            <i data-lucide="sparkles" class="w-4 h-4 text-indigo-500"></i>
                            <span class="text-xs font-bold text-slate-400 uppercase">Summary</span>
                        </div>
                        <p class="text-sm text-slate-700 leading-relaxed">${data.summary || ''}</p>
                    </div>
                </div>

                <!-- Right: Sonic Discussion Side Panel (sticky) -->
                <div class="hidden lg:flex flex-col w-[340px] shrink-0 sticky top-4" id="wr-sonic-sidebar" style="max-height: calc(100vh - 120px);">
                    <div class="bg-gradient-to-br from-teal-600 to-cyan-700 rounded-t-2xl px-4 py-3 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                                <i data-lucide="bot" class="w-4 h-4 text-white"></i>
                            </div>
                            <div>
                                <span class="text-white font-bold text-sm">Coach Nova</span>
                                <span id="wr-sonic-status" class="text-teal-100 text-xs block">Tap mic to discuss this page</span>
                            </div>
                        </div>
                    </div>
                    <div class="bg-slate-900 flex-grow flex flex-col overflow-hidden rounded-b-2xl" style="min-height: 400px;">
                        <div id="wr-transcript" class="flex-grow overflow-y-auto p-4 space-y-3">
                            <div class="px-3 py-2 rounded-xl text-xs text-teal-300 bg-teal-900/50 mr-auto max-w-[90%]">
                                Ask me anything about this page! I can explain concepts, summarize sections, or help with tricky words.
                            </div>
                        </div>
                        <div class="bg-slate-800 px-4 py-3 flex items-center gap-3 border-t border-slate-700">
                            <button id="wr-mic-btn" onclick="app._toggleWrMic()" class="w-11 h-11 rounded-full bg-teal-500 hover:bg-teal-400 text-white flex items-center justify-center transition-colors shrink-0 shadow-lg shadow-teal-500/40">
                                <i data-lucide="mic" class="w-5 h-5"></i>
                            </button>
                            <span class="text-slate-400 text-xs">Tap mic and ask about the page</span>
                            <button onclick="app._closeWrSonic()" class="ml-auto text-red-400 hover:text-red-300 text-xs font-bold">End</button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Mobile: Bottom Sonic FAB (only on small screens) -->
            <button id="wr-sonic-fab" class="lg:hidden fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full bg-gradient-to-br from-teal-500 to-cyan-600 shadow-2xl shadow-teal-500/40 flex items-center justify-center hover:scale-110 transition-transform" onclick="app._openWrSonicMobile()">
                <i data-lucide="bot" class="w-7 h-7 text-white"></i>
            </button>

            <!-- Mobile: Sonic Panel (modal overlay on mobile) -->
            <div id="wr-sonic-mobile" class="hidden lg:hidden fixed inset-0 z-50 bg-black/60 flex items-end justify-center">
                <div class="bg-slate-900 w-full max-w-md rounded-t-2xl flex flex-col" style="max-height: 70vh;">
                    <div class="bg-gradient-to-r from-teal-600 to-cyan-600 rounded-t-2xl px-4 py-3 flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <div class="w-8 h-8 rounded-full bg-white/20 flex items-center justify-center">
                                <i data-lucide="bot" class="w-4 h-4 text-white"></i>
                            </div>
                            <span class="text-white font-bold text-sm">Coach Nova</span>
                        </div>
                        <button onclick="app._closeWrSonicMobile()" class="text-white/60 hover:text-white"><i data-lucide="x" class="w-4 h-4"></i></button>
                    </div>
                    <div id="wr-transcript-mobile" class="flex-grow overflow-y-auto p-4 space-y-3" style="min-height: 200px;"></div>
                    <div class="bg-slate-800 px-4 py-3 flex items-center gap-3 border-t border-slate-700">
                        <button id="wr-mic-btn-mobile" onclick="app._toggleWrMic()" class="w-10 h-10 rounded-full bg-teal-500 text-white flex items-center justify-center shrink-0">
                            <i data-lucide="mic" class="w-5 h-5"></i>
                        </button>
                        <span class="text-slate-400 text-xs">Tap mic to ask</span>
                    </div>
                </div>
            </div>
        `;
    lucide.createIcons();

    // Auto-connect Sonic on desktop (side panel is always visible)
    if (window.innerWidth >= 1024) {
        this._connectWrSonic();
    }
},

_adjustWr(prop, delta) {
    const limits = {
        fontSize: { min: 14, max: 36 },
        letterSpacing: { min: 0, max: 8 },
        wordSpacing: { min: 0, max: 16 },
        lineHeight: { min: 1.2, max: 3.6 }
    };
    let val = this._webReaderCustom[prop] + delta;
    val = Math.max(limits[prop].min, Math.min(limits[prop].max, val));
    this._webReaderCustom[prop] = val;
    const valEl = document.getElementById(`wr-${prop}-val`);
    if (valEl) valEl.innerText = prop === 'lineHeight' ? val.toFixed(1) : val;
    this._applyWebReaderCustomizations();
},

_setWrTheme(theme) {
    this._webReaderCustom.theme = theme;
    if (this._webReaderData) this._renderSimplifiedPage(this._webReaderData);
},

_applyWebReaderCustomizations() {
    const box = document.getElementById('wr-content-box');
    if (!box) return;
    const c = this._webReaderCustom;
    box.style.fontSize = c.fontSize + 'px';
    box.style.letterSpacing = c.letterSpacing + 'px';
    box.style.wordSpacing = c.wordSpacing + 'px';
    box.style.lineHeight = c.lineHeight;
},

// --- Sonic Connection + Audio ---

_openWrSonicMobile() {
    const panel = document.getElementById('wr-sonic-mobile');
    if (panel) panel.classList.remove('hidden');
    lucide.createIcons();
    if (!this._webReaderWs || this._webReaderWs.readyState !== WebSocket.OPEN) {
        this._connectWrSonic();
    }
},

_closeWrSonicMobile() {
    const panel = document.getElementById('wr-sonic-mobile');
    if (panel) panel.classList.add('hidden');
},

_closeWrSonic() {
    this._stopWrMic();
    if (this._webReaderWs) {
        try { this._webReaderWs.send(JSON.stringify({ type: 'stop_audio' })); this._webReaderWs.close(); } catch (e) { }
        this._webReaderWs = null;
    }
    this._webReaderAudioQueue = [];
    this._webReaderPlayingAudio = false;
    if (this._webReaderPlayCtx && this._webReaderPlayCtx.state !== 'closed') {
        try { this._webReaderPlayCtx.close(); } catch (e) { }
    }
    this._webReaderPlayCtx = null;
},

    async _connectWrSonic() {
    const statusEl = document.getElementById('wr-sonic-status');
    if (statusEl) statusEl.innerText = 'Connecting...';

    // Create a persistent playback AudioContext (needs user gesture on some browsers)
    if (!this._webReaderPlayCtx || this._webReaderPlayCtx.state === 'closed') {
        this._webReaderPlayCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
    }
    // Resume it (Chrome requires resume after creation)
    if (this._webReaderPlayCtx.state === 'suspended') {
        await this._webReaderPlayCtx.resume();
    }

    this._webReaderWs = new WebSocket(`${WS_BASE}/webreader/${AppState.learnerId}`);
    this._webReaderWs.binaryType = 'arraybuffer';

    this._webReaderWs.onopen = () => {
        if (statusEl) statusEl.innerText = 'Connected — tap mic to talk';
        this._webReaderWs.send(JSON.stringify({
            type: 'start_audio',
            page_context: this._webReaderData.sonic_context || this._webReaderData.summary || '',
            page_title: this._webReaderData.title || 'Web Page'
        }));
    };

    this._webReaderWs.onmessage = async (event) => {
        if (typeof event.data === 'string') {
            const msg = JSON.parse(event.data);
            if (msg.type === 'transcript') this._addWrBubble(msg.role, msg.text);
            else if (msg.type === 'status' && statusEl) statusEl.innerText = msg.message;
        } else {
            this._queueWrAudio(event.data);
        }
    };

    this._webReaderWs.onclose = () => { if (statusEl) statusEl.innerText = 'Disconnected'; };
},

_addWrBubble(role, text) {
    // Add to both desktop and mobile transcript containers
    const containers = [document.getElementById('wr-transcript'), document.getElementById('wr-transcript-mobile')];
    containers.forEach(container => {
        if (!container) return;
        const isUser = role === 'USER';
        const bubble = document.createElement('div');
        bubble.className = `px-3 py-2 rounded-xl text-sm max-w-[85%] animate-fade-in ${isUser ? 'bg-white/10 text-white/90 ml-auto' : 'bg-teal-500/30 text-teal-100 mr-auto border border-teal-400/20'}`;
        bubble.innerText = text;
        container.appendChild(bubble);
        container.scrollTop = container.scrollHeight;
    });
},

    async _startWrMic() {
    try {
        this._webReaderStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
        const st = document.getElementById('wr-sonic-status');
        if (st) st.innerText = 'Mic access denied';
        return;
    }
    this._webReaderRecording = true;

    // Update both desktop and mobile mic buttons
    ['wr-mic-btn', 'wr-mic-btn-mobile'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) { btn.classList.remove('bg-teal-500'); btn.classList.add('bg-red-500'); }
    });

    if (!this._webReaderAudioCtx || this._webReaderAudioCtx.state === 'closed') {
        this._webReaderAudioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    }
    const source = this._webReaderAudioCtx.createMediaStreamSource(this._webReaderStream);
    const processor = this._webReaderAudioCtx.createScriptProcessor(4096, 1, 1);
    source.connect(processor);
    processor.connect(this._webReaderAudioCtx.destination);
    this._wrProcessor = processor;
    this._wrSource = source;
    processor.onaudioprocess = (e) => {
        if (!this._webReaderRecording || !this._webReaderWs || this._webReaderWs.readyState !== WebSocket.OPEN) return;
        const floatDat = e.inputBuffer.getChannelData(0);
        const pcm16 = new Int16Array(floatDat.length);
        for (let i = 0; i < floatDat.length; i++) {
            let s = Math.max(-1, Math.min(1, floatDat[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        this._webReaderWs.send(pcm16.buffer);
    };
},

_stopWrMic() {
    this._webReaderRecording = false;
    if (this._webReaderStream) { this._webReaderStream.getTracks().forEach(t => t.stop()); this._webReaderStream = null; }
    ['wr-mic-btn', 'wr-mic-btn-mobile'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) { btn.classList.remove('bg-red-500'); btn.classList.add('bg-teal-500'); }
    });
},

_toggleWrMic() {
    if (this._webReaderRecording) {
        this._stopWrMic();
    } else {
        if (!this._webReaderWs || this._webReaderWs.readyState !== WebSocket.OPEN) {
            this._connectWrSonic();
            setTimeout(() => this._startWrMic(), 1500);
        } else {
            this._startWrMic();
        }
    }
},

    async _queueWrAudio(arrayBuffer) {
    this._webReaderAudioQueue.push(arrayBuffer);
    if (!this._webReaderPlayingAudio) this._playNextWrAudio();
},

    async _playNextWrAudio() {
    if (this._webReaderAudioQueue.length === 0) { this._webReaderPlayingAudio = false; return; }
    this._webReaderPlayingAudio = true;
    const buf = this._webReaderAudioQueue.shift();

    try {
        // Reuse persistent playback context instead of creating new ones
        if (!this._webReaderPlayCtx || this._webReaderPlayCtx.state === 'closed') {
            this._webReaderPlayCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 });
        }
        if (this._webReaderPlayCtx.state === 'suspended') {
            await this._webReaderPlayCtx.resume();
        }

        const pcm16 = new Int16Array(buf);
        const audioBuffer = this._webReaderPlayCtx.createBuffer(1, pcm16.length, 24000);
        const f32 = audioBuffer.getChannelData(0);
        for (let i = 0; i < pcm16.length; i++) f32[i] = pcm16[i] / 32768.0;
        const source = this._webReaderPlayCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this._webReaderPlayCtx.destination);
        source.onended = () => this._playNextWrAudio();
        source.start();
    } catch (e) {
        console.error('Audio playback error:', e);
        this._playNextWrAudio();
    }
},

_resetWebReader() {
    this._closeWrSonic();
    this._webReaderData = null;
    this.renderWebReader(document.getElementById('app-container'));
}

};

// Start app
window.addEventListener('DOMContentLoaded', () => {
    app.init();
});
