/* Nova AI front-end: particle core, voice in/out, panels. No external libraries. */
const $ = (s) => document.querySelector(s);
let state = { config: {}, characters: [], memory: [], presets: {} };
let mode = "idle"; // idle | listening | thinking | speaking
let active = false, micMuted = false, rec = null, level = 0;

/* ---------- API ---------- */
function getSessionToken() {
  try {
    if (typeof sessionStorage !== "undefined" && sessionStorage.getItem) {
      return sessionStorage.getItem("nova_token") || "";
    }
  } catch (e) {}
  return "";
}

async function api(path, body) {
  const token = getSessionToken();
  const headers = { "X-Nova-Token": token };
  if (body) {
    headers["Content-Type"] = "application/json";
  }
  const r = await fetch(path, body ? { method: "POST", headers: headers, body: JSON.stringify(body) } : { headers: headers });
  let data = null;
  try {
    data = await r.json();
  } catch (e) {
    data = { ok: false, error: `Server returned HTTP ${r.status}` };
  }
  if (!r.ok && data && typeof data === "object" && !Array.isArray(data)) {
    if (data.ok === undefined) data.ok = false;
    if (!data.error) data.error = `HTTP ${r.status}`;
    data._status = r.status;
  }
  return data;
}

async function streamChat(path, body, onChunk) {
  const token = getSessionToken();
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: {
      "Content-Type": "application/json",
      "X-Nova-Token": token
    },
    body: body ? JSON.stringify(body) : undefined
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    if (onChunk) onChunk(decoder.decode(value, { stream: true }));
  }
}
async function loadState() {
  state = await api("/api/state");
  if ($("#quickLang") && state && state.config && state.config.language) {
    $("#quickLang").value = state.config.language;
  }
  const untrustedBadge = $("#untrustedBadge");
  if (untrustedBadge) {
    if (state && state.is_tainted) {
      untrustedBadge.classList.remove("hidden");
    } else {
      untrustedBadge.classList.add("hidden");
    }
  }
}
if ($("#clearUntrustedBtn")) {
  $("#clearUntrustedBtn").onclick = async (e) => {
    e.stopPropagation();
    await api("/api/clear_untrusted_context", { mode: ModeManager.current });
    await loadState();
    showToast("Context Cleared", "Untrusted tool outputs removed from conversation context.", "info");
  };
}
if ($("#quickLang")) {
  $("#quickLang").onchange = async () => {
    const val = $("#quickLang").value;
    state.config.language = val;
    await api("/api/config", { language: val });
    if (active && !micMuted) {
      if (rec) { try { rec.abort(); } catch {} rec = null; }
      scheduleListen(100);
    }
  };
}

/* ---------- Status / subtitle ---------- */
function setMode(m) {
  mode = m;
  const el = $("#status");
  const colors = {
    idle: "text-[#7fa6b8]",
    listening: "text-[#4dffb0] drop-shadow-[0_0_8px_rgba(77,255,176,0.6)]",
    thinking: "text-[#ffd24d] drop-shadow-[0_0_8px_rgba(255,210,77,0.6)]",
    speaking: "text-[#37d6ff] drop-shadow-[0_0_8px_rgba(55,214,255,0.6)]"
  };
  el.className = `text-xs tracking-[0.25em] flex-1 font-semibold uppercase transition-colors duration-200 ${colors[m] || colors.idle}`;
  const isWake = active && state && state.config && state.config.wake_word_enabled !== false;
  let label = { idle: active ? "STANDBY" : "OFFLINE", listening: "LISTENING", thinking: "THINKING", speaking: "SPEAKING" }[m];
  if (m === "listening" && isWake) {
    label = typeof wakeWordAwake !== "undefined" && wakeWordAwake ? "AWAKE (COMMAND)" : "STANDBY (WAKE WORD)";
  }
  el.textContent = label || "STANDBY";
}
function subtitle(you, nova) {
  $("#subtitle").innerHTML = (you ? `<span class="block text-xs text-[#7fa6b8] mb-1 font-medium">${esc(you)}</span>` : "") + esc(nova || "");
}
const esc = (s) => s == null ? "" : String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const updateClock = () => { $("#clock").textContent = new Date().toLocaleString(); };
updateClock();
setInterval(updateClock, 1000);

/* ---------- Web Audio Synthesizer (Sci-Fi Chimes) ---------- */
let audioCtx = null;
function getAudioCtx() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) audioCtx = new AudioContext();
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  return audioCtx;
}

function playChime(type) {
  try {
    const ctx = getAudioCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    if (type === "activate") {
      const osc1 = ctx.createOscillator();
      const osc2 = ctx.createOscillator();
      const gain = ctx.createGain();
      osc1.type = "sine";
      osc2.type = "sine";
      osc1.frequency.setValueAtTime(587.33, now); // D5
      osc1.frequency.exponentialRampToValueAtTime(880, now + 0.12); // A5
      osc2.frequency.setValueAtTime(880, now);
      osc2.frequency.exponentialRampToValueAtTime(1174.66, now + 0.16); // D6
      gain.gain.setValueAtTime(0.1, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc1.connect(gain);
      osc2.connect(gain);
      gain.connect(ctx.destination);
      osc1.start(now);
      osc2.start(now);
      osc1.stop(now + 0.28);
      osc2.stop(now + 0.28);
    } else if (type === "success") {
      [523.25, 659.25, 783.99, 1046.50].forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(freq, now + i * 0.04);
        gain.gain.setValueAtTime(0.08, now + i * 0.04);
        gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.04 + 0.4);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now + i * 0.04);
        osc.stop(now + i * 0.04 + 0.4);
      });
    } else if (type === "alert") {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.setValueAtTime(330, now + 0.1);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.35);
    }
  } catch (e) {}
}

function showToast(title, msg, type = "normal") {
  const container = $("#toastContainer");
  if (!container) return;
  const el = document.createElement("div");
  const borderColors = {
    normal: "border-l-[#37d6ff] shadow-[0_0_25px_rgba(55,214,255,0.3)]",
    warning: "border-l-[#ffd24d] shadow-[0_0_25px_rgba(255,210,77,0.3)]",
    alert: "border-l-[#ff6b81] shadow-[0_0_25px_rgba(255,107,129,0.3)]"
  };
  el.className = `bg-[#031424]/95 border border-[#37d6ff]/50 border-l-4 p-3.5 rounded shadow-lg w-[min(340px,88vw)] pointer-events-auto transition-opacity duration-300 animate-toastIn ${borderColors[type] || borderColors.normal}`;
  el.innerHTML = `<div class="text-xs font-bold text-[#37d6ff] tracking-wider uppercase mb-1">${esc(title)}</div><div class="text-xs leading-relaxed text-[#e6f7ff]">${esc(msg)}</div>`;
  container.appendChild(el);
  playChime(type === "warning" || type === "alert" ? "alert" : "success");
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.4s";
    setTimeout(() => el.remove(), 400);
  }, 7000);
}

let notifyFailures = 0;
async function pollNotifications() {
  if (notifyFailures > 5) return;
  try {
    const data = await api("/api/notifications");
    notifyFailures = 0;
    if (data && data.notifications && data.notifications.length) {
      for (const n of data.notifications) {
        showToast(n.title, n.message, n.type);
        if ((n.type === "automation" || n.type === "timer") && n.action) {
          send(n.action, n.mode || (typeof ModeManager !== "undefined" ? ModeManager.current : "developer"), {
            is_automation: true,
            automation_token: n.automation_token
          });
        } else if (active && !micMuted) {
          speak(`${n.title}: ${n.message}`);
        }
      }
      try { await api("/api/notifications/clear"); } catch (e) {}
    }
  } catch (e) {
    notifyFailures++;
    if (notifyFailures > 5) {
      setTimeout(() => { notifyFailures = 0; }, 15000);
    }
  }
}
setInterval(pollNotifications, 3000);

/* ---------- Speech output & Multilingual ---------- */
let voices = [];
function updateVoices() {
  if ("speechSynthesis" in window) {
    try { voices = speechSynthesis.getVoices() || []; } catch {}
  }
}
if ("speechSynthesis" in window) {
  speechSynthesis.onvoiceschanged = updateVoices;
  updateVoices();
}

function currentChar() {
  if (!state || !state.characters || !state.characters.length) {
    return { id: "mentor", name: "Mentor", voice: "male" };
  }
  return state.characters.find((c) => c.id === (state.config && state.config.character)) || state.characters[0];
}

function detectTextLanguage(text) {
  if (!text) return state.config.language || "en-US";
  // Bengali
  if (/[\u0980-\u09FF]/.test(text)) return "bn-BD";
  // Hindi / Devanagari
  if (/[\u0900-\u097F]/.test(text)) return "hi-IN";
  // Urdu / Arabic
  if (/[\u0600-\u06FF]/.test(text)) {
    return /[\u067E\u0686\u0698\u06AF\u06BA\u06BE\u06CC]/.test(text) ? "ur-PK" : "ar-SA";
  }
  // Japanese
  if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return "ja-JP";
  // Chinese
  if (/[\u4E00-\u9FFF]/.test(text)) return "zh-CN";
  // Korean
  if (/[\uAC00-\uD7AF]/.test(text)) return "ko-KR";
  // Cyrillic / Russian
  if (/[\u0400-\u04FF]/.test(text)) return "ru-RU";
  // English / Latin
  if (/^[A-Za-z0-9\s.,!?'"()\-:;/_+=@#$%&*~`^<>{}|[\]\\]+$/.test(text.trim())) return "en-US";

  return state.config.language || "en-US";
}

function pickVoiceForLang(langCode) {
  if (!voices.length) updateVoices();
  const char = currentChar();
  const prefix = (langCode || "en").toLowerCase().slice(0, 2);
  let pool = voices.filter((v) => v.lang && v.lang.toLowerCase().startsWith(prefix));
  if (!pool.length) pool = voices;
  const female = /(zira|female|samantha|aria|jenny|susan|hazel|google uk english female|google)/i;
  const male = /(david|male|daniel|guy|mark|alex|google uk english male|james)/i;
  const want = char && char.voice === "female" ? female : male;
  return pool.find((v) => want.test(v.name)) || pool.find((v) => v.lang && v.lang.toLowerCase().startsWith(prefix)) || pool[0] || voices[0];
}

window._activeUtterance = null;
let speechWatchdogTimer = null;
let currentSpeechSession = 0;

function cancelSpeech() {
  currentSpeechSession++;
  if (speechWatchdogTimer) {
    clearInterval(speechWatchdogTimer);
    speechWatchdogTimer = null;
  }
  if ("speechSynthesis" in window) {
    try {
      window.speechSynthesis.cancel();
      window.speechSynthesis.resume();
    } catch {}
  }
  window._activeUtterance = null;
  if (mode === "speaking") setMode("idle");
}

function startSpeechWatchdog() {
  if (speechWatchdogTimer) clearInterval(speechWatchdogTimer);
  speechWatchdogTimer = setInterval(() => {
    if ("speechSynthesis" in window) {
      if (window.speechSynthesis.speaking) {
        try {
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        } catch {}
      }
    }
  }, 5000);
}

function stopSpeechWatchdog() {
  if (speechWatchdogTimer) {
    clearInterval(speechWatchdogTimer);
    speechWatchdogTimer = null;
  }
}

function speak(text) {
  return new Promise(async (resolve) => {
    if (!("speechSynthesis" in window) || !text || !text.trim()) return resolve();
    cancelSpeech();
    const mySession = currentSpeechSession;

    // Split long replies into sentence chunks (including Bengali/Hindi ।, Urdu ۔)
    const rawChunks = text.split(/(?<=[.?!।۔])\s+/).map((c) => c.trim()).filter(Boolean);
    const chunks = rawChunks.length > 0 ? rawChunks : [text.trim()];

    startSpeechWatchdog();

    const cleanup = () => {
      stopSpeechWatchdog();
      window._activeUtterance = null;
      if (mode === "speaking") setMode("idle");
    };

    for (let i = 0; i < chunks.length; i++) {
      if (currentSpeechSession !== mySession) {
        cleanup();
        return resolve();
      }

      const chunk = chunks[i];
      const isLastChunk = i === chunks.length - 1;

      await new Promise((chunkResolve) => {
        if (currentSpeechSession !== mySession) {
          return chunkResolve();
        }

        const u = new SpeechSynthesisUtterance(chunk);
        window._activeUtterance = u;
        const targetLang = detectTextLanguage(chunk);
        const v = pickVoiceForLang(targetLang);
        if (v) {
          u.voice = v;
          const targetPrefix = (targetLang || "en").toLowerCase().slice(0, 2);
          if (v.lang && v.lang.toLowerCase().startsWith(targetPrefix)) {
            u.lang = targetLang;
          } else if (v.lang) {
            u.lang = v.lang;
          } else {
            u.lang = targetLang;
          }
        } else {
          u.lang = targetLang;
        }
        u.rate = state.config.voice_rate != null ? Number(state.config.voice_rate) : 1.02;
        const basePitch = (currentChar() || {}).voice === "female" ? 1.1 : 0.9;
        u.pitch = state.config.voice_pitch != null ? Number(state.config.voice_pitch) : basePitch;
        u.volume = state.config.voice_volume != null ? Number(state.config.voice_volume) : 1.0;

        let finished = false;
        let timeout = null;

        const done = () => {
          if (finished) return;
          finished = true;
          clearTimeout(timeout);
          if (window._activeUtterance === u) {
            window._activeUtterance = null;
          }
          if (isLastChunk) {
            cleanup();
            if (currentSpeechSession === mySession) {
              if (mode === "speaking") setMode("idle");
              scheduleListen(800);
            }
          }
          chunkResolve();
        };

        u.onstart = () => {
          window._speechStartTime = Date.now();
          if (currentSpeechSession === mySession) setMode("speaking");
        };
        u.onend = done;
        u.onerror = (e) => {
          const err = (e && e.error) || e;
          if (err !== "interrupted" && err !== "canceled") {
            console.warn("[Nova AI] Speech error:", err);
          }
          cleanup();
          done();
        };

        // Safety timeout per chunk to prevent hang if speech engine stalls
        timeout = setTimeout(done, Math.max(6000, chunk.length * 120));

        try {
          if (window.speechSynthesis.paused) {
            window.speechSynthesis.resume();
          }
          window.speechSynthesis.speak(u);
        } catch (err) {
          console.warn("[Nova AI] Speech speak failed:", err);
          done();
        }
      });
    }

    cleanup();
    resolve();
  });
}

/* Ask the browser for the microphone up front, so the permission prompt appears right when you click Start
   and we can tell you exactly what is wrong (blocked / no mic) instead of silently not hearing you. */
async function ensureMic() {
  if (navigator.permissions && navigator.permissions.query) {
    try {
      const p = await navigator.permissions.query({ name: "microphone" });
      if (p.state === "denied") {
        return { ok: false, msg: "Microphone blocked in browser. Click the lock/tune icon near the address bar, allow microphone, then click Start AI." };
      }
      if (p.state === "granted") return { ok: true };
    } catch {}
  }
  if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      try { stream.getTracks().forEach((t) => t.stop()); } catch {}
      return { ok: true };
    } catch (e) {
      if (e && (e.name === "NotAllowedError" || e.name === "SecurityError"))
        return { ok: false, msg: "Microphone blocked. Click the lock icon near the address bar, set Microphone to Allow, then press Start AI." };
      if (e && (e.name === "NotFoundError" || e.name === "OverconstrainedError"))
        return { ok: false, msg: "No microphone detected. Connect a microphone or headset and press Start AI." };
      return { ok: false, msg: "Cannot access microphone (" + (e.name || "error") + "). Check Windows sound settings and retry." };
    }
  }
  return { ok: true };
}
let micErrors = 0;
let keepReply = false;
let silenceTimer = null;
let abortStreak = [];
let listenTimer = null;

function scheduleListen(delay = 300) {
  if (listenTimer) {
    clearTimeout(listenTimer);
    listenTimer = null;
  }
  if (!active || micMuted || mode === "thinking" || mode === "speaking") return;
  listenTimer = setTimeout(() => {
    listenTimer = null;
    if (active && !micMuted && (mode === "idle" || mode === "listening") && !rec) {
      startListening();
    }
  }, delay);
}

function micBlocked(msg) {
  active = false;
  $("#start").textContent = "Start AI";
  setMode("idle");
  subtitle("", msg);
}

/* ---------- Speech input ---------- */
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

/* Only ONE speech-recognition session can run in the whole browser. If a second Nova tab (or another page/app)
   starts one, Chrome cancels ours with "aborted", and two tabs would cancel each other forever.
   So: tabs tell each other who owns the microphone, and an "aborted" streak stops with a clear message. */
const tabId = Math.random().toString(36).slice(2);
let bc = null;
try {
  bc = new BroadcastChannel("nova-ai");
  bc.onmessage = (m) => {
    if (m.data && m.data.type === "mic-claim" && m.data.id !== tabId && active) {
      if (rec) { const r = rec; rec = null; try { r.abort(); } catch {} }
      try { speechSynthesis.cancel(); } catch {}
      micBlocked("Voice moved to another Nova tab, so this one stopped listening. Press Start AI here to take it back.");
    }
  };
} catch {}

/* ---------- Wake-Word Engine ---------- */
let wakeWordAwake = false;
let wakeWordAwakeTimer = null;

const WAKE_WORD_RE = /^\s*(hey\s+nova|hi\s+nova|hello\s+nova|ok\s+nova|okay\s+nova|nova|hey\s+jarvis|hi\s+jarvis|hello\s+jarvis|jarvis|হে\s+নোভা|হাই\s+নোভা|হ্যালো\s+নোভা|নোভা|হে\s+জার্ভিস|হাই\s+জার্ভিস|জার্ভিস|নোবা)(?=$|[\s,.:!?;~-])[\s,.:!?;~-]*/i;

function extractWakeWord(rawText) {
  if (!rawText) return { matched: false, wakeWord: "", command: "" };
  const text = rawText.trim();
  const m = text.match(WAKE_WORD_RE);
  if (m) {
    const wakeWord = m[1].toLowerCase();
    const command = text.slice(m[0].length).replace(/^[\s,.:!?;~-]+/, "").trim();
    return { matched: true, wakeWord, command };
  }
  return { matched: false, wakeWord: "", command: text };
}

function startListening() {
  if (!SR) {
    subtitle("", "Speech recognition is not supported in this browser. Please open in Google Chrome or Microsoft Edge.");
    return;
  }
  if (!active || micMuted || mode === "thinking" || mode === "speaking") return;
  if (rec) return;

  const me = new SR();
  rec = me;
  // Each session only controls itself: late events from an old/cancelled session are ignored
  const mine = () => rec === me;
  me.lang = state.config.language || "en-US";
  me.interimResults = true;
  me.continuous = true;
  let finalText = "";
  let interimText = "";

  me.onstart = () => {
    if (!mine()) return;
    setMode("listening");
    const isWake = state.config && state.config.wake_word_enabled !== false;
    if (!keepReply) {
      subtitle("", isWake ? (wakeWordAwake ? "Listening for command…" : "Listening… say 'Hey Nova' or 'Jarvis'.") : "Listening… speak now.");
    }
    console.log("[Nova AI] Microphone active, language:", me.lang, "wake-word enabled:", isWake);
  };
  me.onaudiostart = () => console.log("[Nova AI] Audio capture started");
  me.onspeechstart = () => {
    console.log("[Nova AI] Speech detected");
    if (mode === "speaking") {
      const now = Date.now();
      if (now - (window._speechStartTime || 0) < 600) {
        console.log("[Nova AI] Echo guard: ignoring speech-start within 600ms of speech output");
        return;
      }
      if (state.config && state.config.barge_in_enabled === true) {
        console.log("[Nova AI] Barge-in triggered: cancelling speech synthesis");
        cancelSpeech();
        setMode("listening");
        playChime("activate");
      }
    }
  };
  me.onresult = (e) => {
    if (!mine()) return;
    if (mode === "speaking") {
      const now = Date.now();
      if (now - (window._speechStartTime || 0) < 600) return;
      if (state.config && state.config.barge_in_enabled === true) {
        cancelSpeech();
        setMode("listening");
      } else {
        return;
      }
    }
    abortStreak = [];
    micErrors = 0;
    keepReply = false;
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; ++i) {
      if (e.results[i].isFinal) {
        finalText += (finalText ? " " : "") + e.results[i][0].transcript;
      } else {
        interim += e.results[i][0].transcript;
      }
    }
    const current = (finalText + " " + interim).trim();
    if (!current) return;

    clearTimeout(silenceTimer);
    const isWakeWordMode = state.config && state.config.wake_word_enabled !== false;

    if (isWakeWordMode) {
      if (!wakeWordAwake) {
        const check = extractWakeWord(current);
        if (check.matched) {
          wakeWordAwake = true;
          setMode("listening");
          playChime("activate");
          console.log("[Nova AI] Wake-word matched:", check.wakeWord);

          if (check.command.length > 1) {
            // Wake word + command spoken together: "Hey Nova, open chrome"
            clearTimeout(silenceTimer);
            clearTimeout(wakeWordAwakeTimer);
            finalText = "";
            interimText = "";
            wakeWordAwake = false;
            subtitle(check.command, "Processing…");
            try { me.stop(); } catch {}
            send(check.command);
            return;
          } else {
            // Wake word spoken alone: "Hey Nova" or "Jarvis"
            subtitle(current, "Yes? I'm listening…");
            finalText = "";
            interimText = "";
            clearTimeout(wakeWordAwakeTimer);
            // Stay awake for 7 seconds waiting for the user's command
            wakeWordAwakeTimer = setTimeout(() => {
              wakeWordAwake = false;
              setMode("listening");
              if (active && mode === "listening") {
                subtitle("", "Listening… say 'Hey Nova' or 'Jarvis'.");
              }
            }, 7000);
            return;
          }
        } else {
          // Ambient noise or non-wake speech: do NOT send to AI, prompt user softly
          interimText = current;
          subtitle(current, "Say 'Hey Nova' or 'Jarvis' to activate.");
          return;
        }
      } else {
        // Nova is already awake and recording the user's command
        const check = extractWakeWord(current);
        const actualCommand = check.matched && check.command ? check.command : current;
        interimText = actualCommand;
        subtitle(actualCommand, "Listening…");

        silenceTimer = setTimeout(() => {
          const textToSend = (finalText || interimText).trim();
          if (textToSend && active && !micMuted && mode === "listening") {
            console.log("[Nova AI] Sending wake-word command:", textToSend);
            clearTimeout(wakeWordAwakeTimer);
            wakeWordAwake = false;
            finalText = "";
            interimText = "";
            try { me.stop(); } catch {}
            send(textToSend);
          }
        }, 1200);
        return;
      }
    }

    // Classic continuous listening (wake_word_enabled is false)
    interimText = current;
    subtitle(current, "");
    silenceTimer = setTimeout(() => {
      const textToSend = (finalText || interimText).trim();
      if (textToSend && active && !micMuted && mode === "listening") {
        console.log("[Nova AI] Auto-sending speech:", textToSend);
        finalText = "";
        interimText = "";
        try { me.stop(); } catch {}
        send(textToSend);
      }
    }, 1300);
  };
  me.onerror = (e) => {
    if (e.error === "no-speech") {
      return; // Normal silence; silently ignore so it does not trigger error warnings
    }
    if (e.error !== "aborted") {
      console.warn("[Nova AI] Speech error:", e.error);
    }
    if (!mine()) return;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      micBlocked("Microphone blocked. Click the lock icon in the address bar, set Microphone to Allow, then press Start AI again.");
    } else if (e.error === "audio-capture") {
      micBlocked("No microphone found or another app is using it. Check Windows microphone privacy settings, then press Start AI.");
    } else if (e.error === "language-not-supported") {
      if (me.lang !== "en-US") {
        console.warn("[Nova AI] Language not supported, falling back to en-US");
        state.config.language = "en-US";
        me.lang = "en-US";
        subtitle("", "Language not supported by speech service. Falling back to English (en-US).");
        scheduleListen(600);
      } else {
        micBlocked("This speech language isn't supported by your browser. Please use Chrome or Edge.");
      }
    } else if (e.error === "network") {
      micErrors++;
      subtitle("", "Voice recognition can't reach the browser speech service. Check your internet connection.");
    } else if (e.error === "aborted") {
      const now = Date.now();
      abortStreak.push(now);
      abortStreak = abortStreak.filter((t) => now - t <= 3000);
      if (abortStreak.length >= 3) {
        console.warn("[Nova AI] 3 aborted errors in 3 seconds, stopping microphone loop.");
        abortStreak = [];
        micBlocked("Microphone access was interrupted or is in use by another app. Press Start AI to retry.");
        return;
      }
      console.log("[Nova AI] Recognition aborted momentarily, will resume.");
    }
  };
  me.onend = () => {
    console.log("[Nova AI] Speech recognition ended");
    clearTimeout(silenceTimer);
    if (!mine()) return;
    rec = null;
    const isWakeWordMode = state.config && state.config.wake_word_enabled !== false;
    const textToSend = (finalText || interimText).trim();
    finalText = "";
    interimText = "";

    if (textToSend && active && !micMuted && mode === "listening") {
      if (isWakeWordMode) {
        if (wakeWordAwake) {
          clearTimeout(wakeWordAwakeTimer);
          wakeWordAwake = false;
          send(textToSend);
        } else {
          const check = extractWakeWord(textToSend);
          if (check.matched && check.command.length > 1) {
            send(check.command);
          } else {
            // Discard ambient background sound without sending to LLM
            setMode("idle");
            scheduleListen(300);
          }
        }
      } else {
        send(textToSend);
      }
    } else if (active && !micMuted && mode !== "thinking" && mode !== "speaking") {
      setMode("idle");
      scheduleListen(300);
    } else if (mode === "listening") {
      setMode("idle");
    }
  };
  try {
    me.start();
  } catch (err) {
    console.error("[Nova AI] Failed to start speech recognition:", err);
    rec = null;
    setMode("idle");
    if (active && !micMuted) {
      scheduleListen(1000);
    }
  }
}

function showActionHud(actions) {
  const el = $("#actionHud");
  if (!el) return;
  if (!actions || !actions.length) {
    el.classList.add("hidden");
    return;
  }
  el.innerHTML = actions.map((a) => {
    const isCode = a.skill === "RUN_CODE" || a.skill === "WRITE_FILE" || a.skill === "CMD" || a.skill === "POWERSHELL";
    const title = `${a.skill}${a.arg ? ": " + a.arg.split("\n")[0].slice(0, 50) : ""}`;
    const resultText = a.result || "Done";
    return `<div class="bg-[#031220]/95 border border-[#37d6ff]/40 border-l-4 border-l-[#37d6ff] p-3 rounded shadow-[0_0_20px_rgba(55,214,255,0.25)] text-xs flex flex-col gap-1.5 backdrop-blur-md animate-hudIn">
      <div class="flex items-center justify-between text-[#37d6ff] font-semibold text-[11px] tracking-wider uppercase">
        <span>⚡ ${esc(title)}</span>
        <span class="text-[#4dffb0] font-mono">${isCode ? "Executed" : "Success"}</span>
      </div>
      <div class="text-[#e3f6ff] font-mono text-[11px] max-h-[140px] overflow-y-auto whitespace-pre-wrap bg-black/40 p-2 rounded border border-[#37d6ff]/15 leading-relaxed">${esc(resultText)}</div>
    </div>`;
  }).join("");
  el.classList.remove("hidden");
  clearTimeout(window._hudTimer);
  window._hudTimer = setTimeout(() => {
    el.classList.add("hidden");
  }, 14000);
}

/* ---------- Chat ---------- */
async function send(text, modeOverride, extraOpts = {}) {
  wakeWordAwake = false;
  clearTimeout(wakeWordAwakeTimer);
  if (rec) { try { rec.abort(); } catch {} rec = null; }
  setMode("thinking");
  subtitle(text, "…");
  let res;
  const chatMode = modeOverride || (typeof ModeManager !== "undefined" ? ModeManager.current : "developer") || "developer";
  let slowTimer = setTimeout(() => {
    if (mode === "thinking") {
      const lang = (state.config && state.config.language) || "en-US";
      const waitMessages = {
        "bn": "একটু সময় লাগছে, দয়া করে অপেক্ষা করুন...",
        "hi": "थोड़ा समय लग रहा है, कृपया प्रतीक्षा करें...",
        "es": "Esto está tardando más de lo habitual, un momento...",
        "ur": "تھوڑا وقت لگ رہا ہے، براہ کرم انتظار کریں...",
        "fr": "Cela prend plus de temps que d'habitude, un instant s'il vous plaît...",
        "ar": "يستغرق هذا وقتاً أطول من المعتاد، يرجى الانتظار لحظة...",
        "en": "This is taking longer than usual, please wait a moment..."
      };
      const prefix = lang.slice(0, 2).toLowerCase();
      const waitMsg = waitMessages[prefix] || waitMessages["en"];
      subtitle(text, waitMsg);
      try {
        const u = new SpeechSynthesisUtterance(waitMsg);
        const v = pickVoiceForLang(lang);
        if (v) u.voice = v;
        u.lang = lang;
        window.speechSynthesis.speak(u);
      } catch {}
    }
  }, 12000);
  try { res = await api("/api/chat", { message: text, mode: chatMode, ...extraOpts }); }
  catch (e) { res = { error: "Cannot reach the Nova server." }; }
  clearTimeout(slowTimer);
  if (res.error) {
    subtitle(text, res.error);
    if ($("#actionHud")) $("#actionHud").classList.add("hidden");
    setMode("idle");
    await speak(res.error.slice(0, 140));
  } else {
    subtitle(text, res.reply);
    keepReply = true;
    if (res.actions && res.actions.length) {
      showActionHud(res.actions);
      if (res.actions.some((a) => a.skill === "REMEMBER" || a.skill === "FORGET")) {
        await loadState();
      }
    } else if ($("#actionHud")) {
      $("#actionHud").classList.add("hidden");
    }
    if (res.pending) {
      showConfirmModal(res.pending);
    }
    await speak(res.reply);
  }
  setMode("idle");
  scheduleListen(100);
}

$("#start").onclick = async () => {
  if (!active) {
    active = true;
    wakeWordAwake = false;
    clearTimeout(wakeWordAwakeTimer);
    micErrors = 0;
    keepReply = false;
    abortStreak = [];
    if (bc) { try { bc.postMessage({ type: "mic-claim", id: tabId }); } catch {} }
    $("#start").textContent = "Stop AI";
    await loadState();
    const name = state.config.user_name;
    setMode("idle");
    if (!SR) { subtitle("", "Voice input needs Chrome or Edge. You can still type below."); return; }
    const mic = await ensureMic();
    if (!mic.ok) { micBlocked(mic.msg); return; }
    const hello = name ? `Systems online. Hello ${name}.` : "Systems online. I'm listening.";
    subtitle("", hello);
    await speak(hello);
    setMode("idle");
    scheduleListen(100);
  } else {
    active = false;
    $("#start").textContent = "Start AI";
    cancelSpeech();
    if (rec) { try { rec.abort(); } catch {} rec = null; }
    setMode("idle");
  }
};
$("#mute").onclick = () => {
  micMuted = !micMuted;
  $("#mute").textContent = micMuted ? "Mic off" : "Mic on";
  if (micMuted && rec) { try { rec.abort(); } catch {} rec = null; setMode("idle"); }
  else scheduleListen(100);
};
/* ---------- Mode Manager (Developer Mode vs Cyber Mode) ---------- */
const ModeManager = {
  current: localStorage.getItem("nova_mode") === "cyber" ? "cyber" : "developer",
  get isCyber() {
    return this.current === "cyber";
  },
  apply(notify = false) {
    const isC = this.isCyber;
    document.body.classList.toggle("cyber-mode", isC);
    const btn = $("#btnModeToggle");
    if (btn) {
      btn.textContent = isC ? "Developer Mode" : "Cyber Mode";
      btn.title = isC ? "Switch to Developer Mode" : "Switch to Cyber Mode";
    }
    if (notify) {
      playChime(isC ? "activate" : "success");
      const msg = isC ? "Cyber Mode active. Nova Cyber ready." : "Developer Mode active.";
      subtitle("", msg);
      speak(msg);
    }
  },
  toggle() {
    this.current = this.isCyber ? "developer" : "cyber";
    localStorage.setItem("nova_mode", this.current);
    this.apply(true);
  },
  init() {
    this.apply(false);
    const btn = $("#btnModeToggle");
    if (btn) {
      btn.onclick = () => this.toggle();
    }
  }
};

if ($("#btnMiniMode")) {
  $("#btnMiniMode").onclick = () => {
    const isMini = document.body.classList.toggle("mini-mode");
    $("#btnMiniMode").textContent = isMini ? "🗗 Full HUD" : "🗖 Mini HUD";
  };
}
$("#textform").onsubmit = (e) => {
  e.preventDefault();
  const t = $("#text").value.trim();
  if (t) { $("#text").value = ""; cancelSpeech(); send(t); }
};

/* ---------- Panels ---------- */
function openPanel(name) { $("#panel").classList.remove("hidden"); renderPanel(name); }
$("#close").onclick = () => { clearInterval(window._mobileTimer); $("#panel").classList.add("hidden"); };
document.querySelectorAll("#nodes button").forEach((b) => (b.onclick = () => openPanel(b.dataset.panel)));

async function renderPanel(name) {
  clearInterval(window._mobileTimer);
  await loadState();
  const body = $("#panel-body");
  if (name === "browser") {
    const st = await api("/api/browser/status");
    let html = `<h2>Nova Browser</h2>
      <p class="hint">Your private, dedicated browser for Nova AI. Preserves persistent logins for YouTube, WhatsApp Web, and Telegram Web in data/nova_browser_profile. Nova AI tracks all open tabs so it never duplicates tabs.</p>
      <div class="browser-status-bar">
        <span>Status: <b style="color:${st.running ? '#00e5ff' : '#888'}">${st.running ? '● Running & Connected' : '○ Not Running'}</b></span>
        <button class="btn" id="btnLaunchBrowser">${st.running ? 'Focus / New Tab' : 'Launch Nova Browser'}</button>
      </div>

      <div class="browser-quick-links">
        <label>Quick Open & Login Shortcuts:</label>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px;">
          <button class="btn" id="btnOpenYT" style="background:#cc0000; color:#fff">▶ YouTube</button>
          <button class="btn" id="btnOpenWA" style="background:#25d366; color:#fff">💬 WhatsApp Web</button>
          <button class="btn" id="btnOpenTG" style="background:#229ed9; color:#fff">✈ Telegram Web</button>
        </div>
      </div>

      <label>Open URL or Website:</label>
      <div style="display:flex; gap:8px; margin-bottom:16px;">
        <input id="browserUrl" placeholder="e.g. https://www.google.com or wikipedia.org" style="flex:1">
        <button class="btn" id="btnOpenUrl">Open</button>
      </div>

      <h3>Open Tabs in Nova Browser (${st.tabs ? st.tabs.length : 0})</h3>
      <div id="browserTabsList">
        ${st.tabs && st.tabs.length ? st.tabs.map(t => `
          <div class="browser-tab-row">
            <div style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1">
              <b style="color:#00e5ff">${esc(t.title || 'Untitled')}</b><br>
              <small style="color:#888">${esc(t.url)}</small>
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn" data-act="${t.id}" style="padding:4px 10px; font-size:12px;">Switch</button>
              <button class="btn" data-cls="${t.id}" style="padding:4px 8px; font-size:12px; color:#ff6b81">✕</button>
            </div>
          </div>
        `).join('') : "<p class='hint'>No tabs open yet. Click Launch Nova Browser above or speak a command.</p>"}
      </div>

      <div style="margin-top:20px; border-top:1px solid rgba(55,214,255,0.15); padding-top:12px;">
        <label>Interactive Browser Actions:</label>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input id="browserClickTarget" placeholder="Button / Link text or selector to click" style="flex:1">
          <button class="btn" id="btnDomClick">Click</button>
        </div>
        <div style="display:flex; gap:8px; margin-bottom:8px;">
          <input id="browserTypeText" placeholder="Text to type into active page input" style="flex:1">
          <button class="btn" id="btnDomType">Type</button>
        </div>
        <div style="display:flex; gap:8px;">
          <button class="btn" id="btnDomScrollDown" style="flex:1">Scroll Down</button>
          <button class="btn" id="btnDomScrollUp" style="flex:1">Scroll Up</button>
        </div>
      </div>

      <div style="margin-top:20px; border-top:1px solid rgba(55,214,255,0.15); padding-top:12px;">
        <label>Voice Commands you can say to Nova:</label>
        <div class="row"><span>“Open YouTube in Nova browser”</span></div>
        <div class="row"><span>“Play lofi music on YouTube”</span></div>
        <div class="row"><span>“Click Search” or “Type hello into search”</span></div>
        <div class="row"><span>“Scroll down” or “Scroll to top”</span></div>
        <div class="row"><span>“Switch to my WhatsApp tab”</span></div>
        <div class="row"><span>“Read this open page and research it”</span></div>
      </div>
    `;
    body.innerHTML = html;

    $("#btnLaunchBrowser").onclick = async () => {
      await api("/api/browser/launch", {});
      setTimeout(() => renderPanel("browser"), 1000);
    };
    $("#btnOpenYT").onclick = async () => {
      await api("/api/browser/open", { url: "https://www.youtube.com" });
      setTimeout(() => renderPanel("browser"), 800);
    };
    $("#btnOpenWA").onclick = async () => {
      await api("/api/browser/open", { url: "https://web.whatsapp.com" });
      setTimeout(() => renderPanel("browser"), 800);
    };
    $("#btnOpenTG").onclick = async () => {
      await api("/api/browser/open", { url: "https://web.telegram.org/a/" });
      setTimeout(() => renderPanel("browser"), 800);
    };
    $("#btnOpenUrl").onclick = async () => {
      const u = $("#browserUrl").value.trim();
      if (!u) return;
      await api("/api/browser/open", { url: u });
      $("#browserUrl").value = "";
      setTimeout(() => renderPanel("browser"), 800);
    };
    $("#btnOpenUrl").onkeydown = async (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        $("#btnOpenUrl").click();
      }
    };
    $("#btnDomClick").onclick = async () => {
      const target = $("#browserClickTarget").value.trim();
      if (!target) return;
      await api("/api/browser/interact", { action: "click", value: target });
      playChime("success");
    };
    $("#btnDomType").onclick = async () => {
      const txt = $("#browserTypeText").value.trim();
      if (!txt) return;
      await api("/api/browser/interact", { action: "type", value: txt });
      playChime("success");
    };
    $("#btnDomScrollDown").onclick = async () => {
      await api("/api/browser/interact", { action: "scroll", value: "down" });
    };
    $("#btnDomScrollUp").onclick = async () => {
      await api("/api/browser/interact", { action: "scroll", value: "up" });
    };
    body.querySelectorAll("[data-act]").forEach(b => {
      b.onclick = async () => {
        await api("/api/browser/activate", { tab_id: b.dataset.act });
        renderPanel("browser");
      };
    });
    body.querySelectorAll("[data-cls]").forEach(b => {
      b.onclick = async () => {
        await api("/api/browser/close", { tab_id: b.dataset.cls });
        setTimeout(() => renderPanel("browser"), 300);
      };
    });
    return;
  }
  if (name === "brain") {
    const data = await api("/api/notes");
    const notes = data.notes || [];
    body.innerHTML = `<h2>Second Brain (SQLite Knowledge Base)</h2>
      <p class="hint">Permanent, local semantic storage for your notes, documentation, thoughts, and ideas. Stored in data/nova_brain.db.</p>
      
      <div style="display:flex; gap:8px; margin-bottom:14px;">
        <input id="noteSearch" placeholder="🔍 Search notes with semantic BM25 ranking..." style="flex:1">
        <button class="btn" id="btnSearchNotes">Search</button>
      </div>

      <div style="border:1px solid rgba(55,214,255,0.25); padding:12px; border-radius:4px; margin-bottom:18px; background:rgba(0,10,20,0.4)">
        <h3 style="margin-top:0; font-size:12px; letter-spacing:.15em; color:var(--c)">CREATE / SAVE NOTE</h3>
        <label>Title</label>
        <input id="noteTitle" placeholder="e.g. Project Nova Architecture">
        <label>Category</label>
        <input id="noteCategory" placeholder="e.g. work / ideas / tech" value="general">
        <label>Content</label>
        <textarea id="noteContent" placeholder="Write anything here..."></textarea>
        <br><br>
        <button class="btn" id="btnSaveNote">Save to Second Brain</button>
      </div>

      <h3>Stored Notes (${notes.length})</h3>
      <div id="notesList">
        ${notes.length ? notes.map(n => `
          <div class="note-card">
            <div class="note-header">
              <span class="note-title">${esc(n.title)}</span>
              <span class="note-cat">${esc(n.category || 'general')}</span>
            </div>
            <div class="note-body">${esc(n.content)}</div>
            <div style="margin-top:8px; text-align:right">
              <button class="btn" data-delnote="${n.id}" style="padding:2px 8px; font-size:11px; color:#ff6b81">Delete</button>
            </div>
          </div>
        `).join('') : "<p class='hint'>No notes saved yet. Say 'Nova, save note...' or type above.</p>"}
      </div>
    `;

    $("#btnSaveNote").onclick = async () => {
      const t = $("#noteTitle").value.trim();
      const c = $("#noteContent").value.trim();
      const cat = $("#noteCategory").value.trim() || "general";
      if (!t || !c) return;
      await api("/api/notes/save", { title: t, content: c, category: cat });
      playChime("success");
      renderPanel("brain");
    };

    $("#btnSearchNotes").onclick = async () => {
      const q = $("#noteSearch").value.trim();
      const res = await api(`/api/notes?q=${encodeURIComponent(q)}`);
      const list = $("#notesList");
      const found = res.notes || [];
      list.innerHTML = found.length ? found.map(n => `
        <div class="note-card">
          <div class="note-header">
            <span class="note-title">${esc(n.title)} ${n.score ? `(Score: ${n.score})` : ''}</span>
            <span class="note-cat">${esc(n.category || 'general')}</span>
          </div>
          <div class="note-body">${esc(n.content)}</div>
          <div style="margin-top:8px; text-align:right">
            <button class="btn" data-delnote="${n.id}" style="padding:2px 8px; font-size:11px; color:#ff6b81">Delete</button>
          </div>
        </div>
      `).join('') : "<p class='hint'>No notes matched your search.</p>";
      body.querySelectorAll("[data-delnote]").forEach(b => {
        b.onclick = async () => {
          await api("/api/notes/delete", { id: b.dataset.delnote });
          renderPanel("brain");
        };
      });
    };

    body.querySelectorAll("[data-delnote]").forEach(b => {
      b.onclick = async () => {
        await api("/api/notes/delete", { id: b.dataset.delnote });
        renderPanel("brain");
      };
    });
    return;
  }
  if (name === "schedule") {
    const tData = await api("/api/timers");
    const timers = tData.timers || [];
    body.innerHTML = `<h2>Schedule, Timers & Hardware Watchdog</h2>
      <p class="hint">Active countdown timers, reminders, and system health status monitored automatically in the background.</p>

      <div style="display:flex; gap:10px; margin-bottom:16px;">
        <button class="btn" id="btnTriggerBriefing" style="flex:1; background:linear-gradient(90deg,var(--c),var(--c2)); color:#00131c; font-weight:700">☀️ Run Morning Briefing Now</button>
      </div>

      <div style="border:1px solid rgba(55,214,255,0.25); padding:12px; border-radius:4px; margin-bottom:18px; background:rgba(0,10,20,0.4)">
        <h3 style="margin-top:0; font-size:12px; letter-spacing:.15em; color:var(--c)">SET NEW TIMER / REMINDER</h3>
        <label>Delay or Time (e.g. 5m, 30s, 1h, or 18:30)</label>
        <input id="timerSpec" placeholder="e.g. 10m or 15:30">
        <label>Reminder Message</label>
        <input id="timerMsg" placeholder="e.g. Check oven or Team standup">
        <br><br>
        <button class="btn" id="btnAddTimer">Add Timer</button>
      </div>

      <h3>Active Timers & Reminders (${timers.length})</h3>
      <div id="timersList">
        ${timers.length ? timers.map(t => `
          <div class="timer-card">
            <div>
              <b style="color:#fff">${esc(t.message)}</b><br>
              <small style="color:var(--dim)">Due at ${t.due_time} (in ${t.remaining_seconds}s)</small>
            </div>
            <button class="btn" data-canceltimer="${t.id}" style="padding:4px 10px; font-size:12px; color:#ff6b81">Cancel</button>
          </div>
        `).join('') : "<p class='hint'>No active timers right now. Say 'Nova, set a timer for 10 minutes' or add one above.</p>"}
      </div>

      <div style="margin-top:20px; border-top:1px solid rgba(55,214,255,0.15); padding-top:14px;">
        <label>Hardware Watchdog Active Protection:</label>
        <p class="hint">Nova monitors your battery (&lt;20%), RAM usage (&gt;92%), and low disk space (&lt;4GB) in the background and will speak/notify you proactively if critical levels are reached.</p>
      </div>
    `;

    $("#btnTriggerBriefing").onclick = () => {
      send("Give me my morning briefing");
      $("#panel").classList.add("hidden");
    };

    $("#btnAddTimer").onclick = async () => {
      const s = $("#timerSpec").value.trim();
      const m = $("#timerMsg").value.trim() || "Reminder";
      if (!s) return;
      await api("/api/timers/add", { spec: s, message: m });
      playChime("success");
      renderPanel("schedule");
    };

    body.querySelectorAll("[data-canceltimer]").forEach(b => {
      b.onclick = async () => {
        await api("/api/timers/cancel", { id: b.dataset.canceltimer });
        renderPanel("schedule");
      };
    });
    return;
  }
  if (name === "automations") {
    const aData = await api("/api/automations");
    const automations = aData.automations || [];
    body.innerHTML = `<h2>Scheduled Background Automations</h2>
      <p class="hint">Create recurring background tasks that run automatically (e.g. daily weather briefings, system health checks, or automated scripts).</p>

      <div style="border:1px solid rgba(55,214,255,0.25); padding:12px; border-radius:4px; margin-bottom:18px; background:rgba(0,10,20,0.4)">
        <h3 style="margin-top:0; font-size:12px; letter-spacing:.15em; color:var(--c)">ADD RECURRING AUTOMATION</h3>
        <label>Schedule (e.g. every 1h, every 30m, daily 09:00, 18:30)</label>
        <input id="autoSpec" placeholder="e.g. every 1h or daily 09:00">
        <label>Skill Action or Command to Execute</label>
        <input id="autoAction" placeholder="e.g. BRIEFING or SYSTEM: stats">
        <label>Description Label</label>
        <input id="autoLabel" placeholder="e.g. Hourly System Health Check">
        <br><br>
        <button class="btn" id="btnAddAuto">Schedule Automation</button>
      </div>

      <h3>Active Recurring Automations (${automations.length})</h3>
      <div id="automationsList">
        ${automations.length ? automations.map(a => `
          <div class="timer-card">
            <div>
              <b style="color:#fff">${esc(a.label || a.action)}</b><br>
              <small style="color:var(--dim)">Schedule: ${esc(a.spec)} | Next run at ${a.next_run_time} (in ${a.remaining_seconds}s)</small>
            </div>
            <button class="btn" data-cancelauto="${a.id}" style="padding:4px 10px; font-size:12px; color:#ff6b81">Delete</button>
          </div>
        `).join('') : "<p class='hint'>No recurring automations set yet. Add one above or say 'Nova, automate every 1 hour system stats'.</p>"}
      </div>
    `;

    $("#btnAddAuto").onclick = async () => {
      const s = $("#autoSpec").value.trim();
      const a = $("#autoAction").value.trim();
      const l = $("#autoLabel").value.trim() || a;
      if (!s || !a) return;
      await api("/api/automations/add", { spec: s, action: a, label: l });
      playChime("success");
      renderPanel("automations");
    };

    body.querySelectorAll("[data-cancelauto]").forEach(b => {
      b.onclick = async () => {
        await api("/api/automations/cancel", { id: b.dataset.cancelauto });
        renderPanel("automations");
      };
    });
    return;
  }
  if (name === "mobile") {
    const st = await api("/api/remote");
    const on = st.enabled && st.active;
    let html = `<h2>Mobile remote</h2><p class="hint">Control Nova from your phone: scan the QR code, then type (or dictate) commands on the phone and Nova runs them on this PC. Your phone and this PC must be on the same Wi-Fi.</p>`;
    if (st.error) html += `<p class="hint" style="color:#ff6b81">${esc(st.error)}</p>`;
    if (on && !st.urls.length) {
      html += `<p class="hint" style="color:#ffd24d">Couldn't find this PC's Wi-Fi/network address. Connect to Wi-Fi and reopen this panel.</p><button class="btn" id="mobOff">Turn off</button>`;
    } else if (on) {
      html += `<div class="qrwrap"><canvas id="qr"></canvas></div>
        ${st.urls.length > 1 ? `<label>Network (pick the one your phone is on)</label><select id="qrurl">${st.urls.map((u, i) => `<option value="${i}">${esc(u.replace(/\/\?t=.*/, ""))}</option>`).join("")}</select>` : ""}
        <label>Or type this link in your phone browser</label><input id="qrlink" readonly>
        <p class="hint" id="phonestat"></p>
        <p class="hint"><b>1.</b> Open your phone camera (or any QR scanner) <b>2.</b> Scan this code <b>3.</b> Tap the link. Anyone who scans this code can control Nova, so don't share a screenshot of it.</p>
        <button class="btn" id="regen">Make a new code (disconnects old phones)</button> <button class="btn" id="mobOff">Turn off</button>`;
    } else {
      html += `<button class="btn" id="mobOn">Turn on mobile remote</button>
        <p class="hint">The first time on Windows you may see a firewall prompt: allow Python on <b>Private networks</b>. Nothing is reachable from outside your Wi-Fi.</p>`;
    }
    body.innerHTML = html;
    if ($("#mobOn")) $("#mobOn").onclick = async () => { await api("/api/remote/enable", { enabled: true }); renderPanel("mobile"); };
    if ($("#mobOff")) $("#mobOff").onclick = async () => { await api("/api/remote/enable", { enabled: false }); renderPanel("mobile"); };
    if ($("#regen")) $("#regen").onclick = async () => { await api("/api/remote/regenerate", {}); renderPanel("mobile"); };
    if ($("#qr")) {
      const draw = () => {
        const url = st.urls[$("#qrurl") ? +$("#qrurl").value : 0];
        try { NovaQR.draw($("#qr"), url, 6); } catch (e) { body.insertAdjacentHTML("beforeend", "<p class='hint'>QR failed: " + esc(e.message) + "</p>"); }
        $("#qrlink").value = url;
      };
      draw();
      if ($("#qrurl")) $("#qrurl").onchange = draw;
      $("#qrlink").onfocus = (e) => e.target.select();
      const upd = async () => {
        const el = $("#phonestat"); if (!el) return;
        const s = await api("/api/remote");
        const a = s.seconds_since_phone;
        el.textContent = a == null ? "No phone has connected yet." : a < 25 ? "📱 Phone connected" : "Last phone activity " + Math.round(a) + "s ago";
      };
      upd();
      window._mobileTimer = setInterval(upd, 3000);
    }
    try {
      const devRes = await api("/api/remote/devices");
      if (devRes && devRes.devices && devRes.devices.length) {
        let devHtml = `<div style="margin-top:20px;border-top:1px solid rgba(55,214,255,0.2);padding-top:15px;">
          <h3 style="font-size:14px;color:#37d6ff;margin-bottom:8px;">Paired Devices</h3>
          <ul style="list-style:none;padding:0;margin:0;">`;
        devRes.devices.forEach(d => {
          devHtml += `<li style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">
            <span>${esc(d.name)} (${esc(d.client_ip || "IP")})</span>
            <button class="btn btn-sm revoke-btn" data-dev-id="${esc(d.id)}" style="padding:2px 8px;font-size:11px;">Revoke</button>
          </li>`;
        });
        devHtml += `</ul></div>`;
        body.insertAdjacentHTML("beforeend", devHtml);
        body.querySelectorAll(".revoke-btn").forEach(btn => {
          btn.onclick = async () => {
            await api("/api/remote/devices/revoke", { id: btn.dataset.devId });
            renderPanel("mobile");
          };
        });
      }
    } catch (e) {}
    return;
  }
  if (name === "doctor") {
    body.innerHTML = `<h2>System Doctor & Health Diagnostics</h2><p class="hint">Real-time health audit across storage, database, AI providers, and security subsystems.</p><div id="doctorContent"><p class="hint">Running diagnostics...</p></div><br><button class="btn" id="refreshDoctor">Re-run Doctor</button>`;
    const runDoc = async () => {
      const el = $("#doctorContent");
      if (!el) return;
      try {
        const diag = await api("/api/health");
        let h = `<div style="margin-bottom:12px; font-weight:bold; color:${diag.overall_status === 'healthy' ? '#2ed573' : (diag.overall_status === 'degraded' ? '#ffa502' : '#ff4757')}">OVERALL STATUS: ${esc(diag.overall_status.toUpperCase())} (${diag.summary.ok} passed, ${diag.summary.warning} warnings, ${diag.summary.error} errors)</div>`;
        h += `<div style="display:flex; flex-direction:column; gap:8px;">`;
        for (const c of diag.checks) {
          const col = c.status === 'ok' ? '#2ed573' : (c.status === 'warning' ? '#ffa502' : (c.status === 'error' ? '#ff4757' : '#37d6ff'));
          const tag = c.status === 'ok' ? '[OK]' : (c.status === 'warning' ? '[WARN]' : (c.status === 'error' ? '[ERR]' : '[INFO]'));
          h += `<div style="display:flex; justify-content:space-between; align-items:center; background:rgba(0,0,0,0.3); padding:8px 12px; border-radius:4px; border-left:3px solid ${col};"><span style="color:#cfe9f5"><b style="color:${col}">${tag}</b> <b>${esc(c.category)}:</b> ${esc(c.name)}</span><span style="color:#7fa6b8; font-size:11px;">${esc(c.message)}</span></div>`;
        }
        h += `</div>`;
        el.innerHTML = h;
      } catch (e) {
        el.innerHTML = `<p class="hint" style="color:#ff4757">Failed to run diagnostics: ${esc(e.message)}</p>`;
      }
    };
    runDoc();
    if ($("#refreshDoctor")) $("#refreshDoctor").onclick = runDoc;
    return;
  }
  if (name === "usage") {
    body.innerHTML = `<h2>Token Usage & Budget Tracker</h2><p class="hint">Monitors prompt & completion tokens, estimated USD spend, and monthly budget limits.</p><div id="usageContent"><p class="hint">Loading metrics...</p></div>`;
    const loadUsage = async () => {
      const el = $("#usageContent");
      if (!el) return;
      try {
        const data = await api("/api/metrics/usage");
        const s = data.summary || {};
        const b = data.budget || {};
        let h = `<div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:16px;">
          <div style="background:rgba(55,214,255,0.08); padding:10px; border-radius:4px; border:1px solid rgba(55,214,255,0.2);"><div style="font-size:11px; color:#7fa6b8;">TOTAL TOKENS</div><div style="font-size:18px; font-weight:bold; color:#37d6ff;">${(s.total_tokens || 0).toLocaleString()}</div></div>
          <div style="background:rgba(55,214,255,0.08); padding:10px; border-radius:4px; border:1px solid rgba(55,214,255,0.2);"><div style="font-size:11px; color:#7fa6b8;">TOTAL REQUESTS</div><div style="font-size:18px; font-weight:bold; color:#37d6ff;">${(s.total_requests || 0).toLocaleString()}</div></div>
          <div style="background:rgba(55,214,255,0.08); padding:10px; border-radius:4px; border:1px solid rgba(55,214,255,0.2);"><div style="font-size:11px; color:#7fa6b8;">TOTAL SPEND (USD)</div><div style="font-size:18px; font-weight:bold; color:#2ed573;">$${(s.total_cost_usd || 0).toFixed(4)}</div></div>
          <div style="background:rgba(55,214,255,0.08); padding:10px; border-radius:4px; border:1px solid rgba(55,214,255,0.2);"><div style="font-size:11px; color:#7fa6b8;">MONTH SPEND</div><div style="font-size:18px; font-weight:bold; color:#2ed573;">$${(s.current_month_cost_usd || 0).toFixed(4)}</div></div>
        </div>`;
        if (b.budget_active) {
          const barCol = b.exhausted ? '#ff4757' : (b.warning ? '#ffa502' : '#2ed573');
          h += `<div style="background:rgba(0,0,0,0.3); padding:12px; border-radius:4px; margin-bottom:16px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:12px;"><span style="color:#cfe9f5;">Monthly Budget ($${b.cap_usd})</span><span style="color:${barCol}; font-weight:bold;">${b.percent_used}% Used ($${b.remaining_usd} remaining)</span></div>
            <div style="background:rgba(255,255,255,0.1); height:8px; border-radius:4px; overflow:hidden;"><div style="background:${barCol}; width:${Math.min(100, b.percent_used)}%; height:100%;"></div></div>
          </div>`;
        }
        h += `<h4 style="color:#37d6ff; margin:12px 0 6px 0;">Usage by Model</h4><div style="display:flex; flex-direction:column; gap:6px;">`;
        for (const [mod, info] of Object.entries(s.by_model || {})) {
          h += `<div style="display:flex; justify-content:space-between; background:rgba(0,0,0,0.2); padding:6px 10px; border-radius:4px; font-size:11px;"><span style="color:#cfe9f5;">${esc(mod)} (${info.requests} reqs)</span><span style="color:#7fa6b8;">${info.tokens.toLocaleString()} tokens &bull; $${info.cost_usd.toFixed(4)}</span></div>`;
        }
        h += `</div>`;
        el.innerHTML = h;
      } catch (e) {
        el.innerHTML = `<p class="hint" style="color:#ff4757">Failed to load metrics: ${esc(e.message)}</p>`;
      }
    };
    loadUsage();
    return;
  }

  if (name === "github") {
    body.innerHTML = `<h2>GitHub & Repository Tools</h2>
      <p class="hint">Inspect any GitHub repository, browse READMEs, view open issues/PRs, browse file trees, clone repos into workspace, and install skills.</p>
      
      <label>Target Repository (owner/repo):</label>
      <div style="display:flex; gap:8px; margin-bottom:12px;">
        <input id="ghRepo" placeholder="e.g. pocketpaw/pocketpaw" value="pocketpaw/pocketpaw" style="flex:1">
      </div>

      <div style="display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px;">
        <button class="btn" id="btnGhInfo">📘 Overview</button>
        <button class="btn" id="btnGhReadme">📖 README</button>
        <button class="btn" id="btnGhIssues">🐛 Issues</button>
        <button class="btn" id="btnGhPrs">🔀 Pull Requests</button>
        <button class="btn" id="btnGhTree">🌳 File Tree</button>
        <button class="btn" id="btnGhClone" style="color:#2ed573;">📥 Clone to Workspace</button>
        <button class="btn" id="btnGhSkills" style="color:#37d6ff;">⚡ Install Skills</button>
      </div>

      <div style="display:flex; gap:8px; margin-bottom:12px; align-items:center;">
        <label style="margin:0; white-space:nowrap; font-size:11px;">Inspect Specific File:</label>
        <input id="ghFilePath" placeholder="path/to/file.py (e.g. src/pocketpaw/budget.py)" style="flex:1">
        <button class="btn" id="btnGhFile">View File</button>
      </div>

      <label>Repository Output:</label>
      <div id="ghOutput" style="background:rgba(0,0,0,0.5); border:1px solid rgba(55,214,255,0.25); border-radius:4px; padding:12px; font-family:monospace; font-size:11px; color:#cfe9f5; min-height:160px; max-height:48vh; overflow-y:auto; white-space:pre-wrap; word-break:break-all;">Click any action above to inspect the repository.</div>`;

    const execGh = async (action, filePath = "") => {
      const out = $("#ghOutput");
      const repo = $("#ghRepo").value.trim();
      if (!repo) {
        out.textContent = "Please enter a valid repository name (e.g. pocketpaw/pocketpaw).";
        return;
      }
      out.textContent = `Executing '${action}' on ${repo}...`;
      try {
        let res;
        if (action === "clone" || action === "install_skills") {
          res = await api("/api/github", { repo: repo, action: action });
        } else {
          let url = `/api/github?repo=${encodeURIComponent(repo)}&action=${encodeURIComponent(action)}`;
          if (filePath) url += `&path=${encodeURIComponent(filePath)}`;
          res = await api(url);
        }
        out.textContent = res.result || JSON.stringify(res, null, 2);
      } catch (e) {
        out.textContent = "Error executing GitHub action: " + (e.message || e);
      }
    };

    if ($("#btnGhInfo")) $("#btnGhInfo").onclick = () => execGh("info");
    if ($("#btnGhReadme")) $("#btnGhReadme").onclick = () => execGh("readme");
    if ($("#btnGhIssues")) $("#btnGhIssues").onclick = () => execGh("issues");
    if ($("#btnGhPrs")) $("#btnGhPrs").onclick = () => execGh("prs");
    if ($("#btnGhTree")) $("#btnGhTree").onclick = () => execGh("tree");
    if ($("#btnGhClone")) $("#btnGhClone").onclick = () => execGh("clone");
    if ($("#btnGhSkills")) $("#btnGhSkills").onclick = () => execGh("install_skills");
    if ($("#btnGhFile")) $("#btnGhFile").onclick = () => execGh("file", $("#ghFilePath").value.trim());
    return;
  }

  if (name === "audit") {
    body.innerHTML = `<h2>Security Audit Trail</h2><p class="hint">Append-only security log recording every tool invocation, channel, guardian safety verdict, and confirmation status.</p><div id="auditContent"><p class="hint">Loading audit events...</p></div><br><button class="btn" id="refreshAudit">Refresh Audit Log</button>`;
    const loadAudit = async () => {
      const el = $("#auditContent");
      if (!el) return;
      try {
        const res = await api("/api/audit?limit=50");
        const events = res.events || [];
        if (!events.length) {
          el.innerHTML = `<p class="hint">No audit events recorded yet. Perform an action to see it logged.</p>`;
          return;
        }
        let h = `<div style="display:flex; flex-direction:column; gap:8px; max-height:55vh; overflow-y:auto;">`;
        for (const ev of events.slice().reverse()) {
          const stUpper = (ev.status || "UNKNOWN").toUpperCase();
          const isAllowed = stUpper === "EXECUTED" || stUpper === "ALLOWED" || stUpper === "APPROVED" || stUpper === "AUTO_APPROVED" || stUpper === "APPROVED_USER";
          const stCol = isAllowed ? "#2ed573" : (stUpper === "AWAITING_CONFIRMATION" ? "#ffa502" : "#ff4757");
          const toolName = ev.tool || "SYSTEM";
          const chan = ev.channel || "pc";
          const rawVerdict = ev.guardian || ev.guardian_verdict || "NONE";
          const verdictNorm = String(rawVerdict).replace(/^\[|\]$/g, "").toUpperCase();
          const verdictCol = verdictNorm === "SAFE" ? "#2ed573" : (verdictNorm === "DANGEROUS" ? "#ff4757" : "#7fa6b8");
          const timeStr = ev.timestamp ? ev.timestamp.replace("T", " ").slice(0, 19) : "";
          h += `<div style="background:rgba(0,0,0,0.3); padding:8px 12px; border-radius:4px; border-left:3px solid ${stCol}; font-size:11px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <span style="color:#37d6ff; font-weight:bold;">${esc(toolName)} <small style="color:#7fa6b8; font-weight:normal;">via [${esc(chan)}]</small></span>
              <span style="color:${stCol}; font-weight:bold;">${esc(stUpper)}</span>
            </div>
            <div style="color:#cfe9f5; font-family:monospace; margin-bottom:4px; word-break:break-all;">${esc(ev.preview || "")}</div>
            <div style="display:flex; justify-content:space-between; color:#7fa6b8; font-size:10px;">
              <span>Guardian: <b style="color:${verdictCol}">${esc(verdictNorm)}</b></span>
              <span>${esc(timeStr)}</span>
            </div>
          </div>`;
        }
        h += `</div>`;
        el.innerHTML = h;
      } catch (e) {
        el.innerHTML = `<p class="hint" style="color:#ff4757">Failed to load audit events: ${esc(e.message)}</p>`;
      }
    };
    loadAudit();
    if ($("#refreshAudit")) $("#refreshAudit").onclick = loadAudit;
    return;
  }

  if (name === "memory") {
    body.innerHTML = `<h2>Memory</h2><p class="hint">Nova saves lasting facts about you here (say "remember that I…"). Stored only on this PC in data/memory.json.</p>
      ${state.memory.map((m, i) => {
        const text = (typeof m === 'object' && m !== null) ? (m.text || '') : m;
        const isTainted = (typeof m === 'object' && m !== null && m.tainted);
        const badge = isTainted ? ' <span style="color:#ff6b6b;font-size:10px;">[untrusted source]</span>' : '';
        return `<div class="row"><span>${esc(text)}${badge}</span><button data-del="${i}">delete</button></div>`;
      }).join("") || "<p class='hint'>Nothing yet.</p>"}
      <label>Add a memory</label><input id="newmem" placeholder="e.g. My sister's name is Ayesha"><br><br><button class="btn" id="addmem">Add</button>`;
    const addMem = async () => {
      const val = $("#newmem").value.trim();
      if (!val) return;
      await api("/api/memory/add", { text: val });
      renderPanel("memory");
    };
    body.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => { await api("/api/memory/delete", { index: +b.dataset.del }); renderPanel("memory"); }));
    $("#addmem").onclick = addMem;
    $("#newmem").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); addMem(); } };
  }
  if (name === "characters") {
    body.innerHTML = `<h2>Character</h2><p class="hint">Pick who Nova is, or create your own.</p>
      ${state.characters.map((c) => `<div class="char ${c.id === state.config.character ? "on" : ""}" data-id="${c.id}"><b>${esc(c.name)}</b> · ${c.voice}<small>${esc(c.prompt.slice(0, 110))}…</small></div>`).join("")}
      <h2 style="margin-top:20px">Create</h2>
      <label>Name</label><input id="cname"><label>Voice</label><select id="cvoice"><option>male</option><option>female</option></select>
      <label>Personality</label><textarea id="cprompt" placeholder="You are a ..."></textarea><br><br><button class="btn" id="cadd">Save character</button>`;
    body.querySelectorAll(".char").forEach((el) => (el.onclick = async () => { await api("/api/config", { character: el.dataset.id }); renderPanel("characters"); }));
    $("#cadd").onclick = async () => {
      const c = { name: $("#cname").value, voice: $("#cvoice").value, prompt: $("#cprompt").value };
      if (!c.name || !c.prompt) return;
      await api("/api/characters", { characters: [...state.characters, c] });
      renderPanel("characters");
    };
  }
  if (name === "workspace") {
    let taintedList = [];
    try {
      const tRes = await api("/api/workspace/tainted");
      taintedList = (tRes && tRes.files) ? tRes.files : [];
    } catch (e) {}
    body.innerHTML = `<h2>Coding Workspace</h2>
      <p class="hint">This is the dedicated folder where Nova creates code files, scripts, and projects for you.</p>
      <div class="workspace-bar">
        <span>📁 Path:</span>
        <span class="workspace-path">${esc(state.workspace || "workspace")}</span>
        <button class="btn" id="btnOpenWs">Open in Explorer</button>
      </div>
      <div id="taintedFilesSection" style="margin:14px 0; padding:10px 12px; border:1px solid rgba(255,107,129,0.35); border-radius:4px; background:rgba(255,71,87,0.06);">
        <h3 style="margin:0 0 6px 0; font-size:12px; color:#ff6b81; letter-spacing:0.1em; text-transform:uppercase;">🛡️ Untrusted / Tainted Files (${taintedList.length})</h3>
        <p class="hint" style="margin:0 0 8px 0;">Files written during untrusted/tainted turns require confirmation before execution or opening until you explicitly trust their current SHA-256 content.</p>
        ${taintedList.length ? taintedList.map(f => `
          <div class="row" style="display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.06);">
            <div style="overflow:hidden; text-overflow:ellipsis;">
              <b style="color:#ff6b81">${esc(f.name)}</b>
              <small style="display:block; color:#7fa6b8; font-family:monospace; font-size:10px;">SHA-256: ${esc((f.sha256 || '').slice(0, 16))}…</small>
            </div>
            <button class="btn trust-file-btn" data-trust-path="${esc(f.path || f.name)}" style="padding:3px 10px; font-size:11px; color:#4dffb0;">Trust File</button>
          </div>
        `).join("") : "<p class='hint' style='margin:0;'>No tainted files in workspace.</p>"}
      </div>
      <label>Voice coding examples you can try:</label>
      <div class="row"><span>“Write a Python script calculator.py with functions for math operations”</span></div>
      <div class="row"><span>“Create an index.html and style.css for a modern dark-mode landing page”</span></div>
      <div class="row"><span>“Run python calculator.py and test it”</span></div>
      <div class="row"><span>“Install requests and beautifulsoup4 using pip”</span></div>
      <div class="row"><span>“List all files in my workspace”</span></div>`;
    if ($("#btnOpenWs")) {
      $("#btnOpenWs").onclick = async () => {
        await api("/api/workspace/open");
      };
    }
    body.querySelectorAll(".trust-file-btn").forEach(btn => {
      btn.onclick = async () => {
        const p = btn.dataset.trustPath;
        const r = await api("/api/workspace/trust", { path: p });
        if (r && r.ok) {
          showToast("File Trusted", `Cleared taint mark for ${p}`, "normal");
          renderPanel("workspace");
        } else {
          showToast("Error", (r && r.error) || "Could not trust file", "alert");
        }
      };
    });
  }
  if (name === "skills") {
    body.innerHTML = `<h2>Nova AI Skills & Powers</h2>
      <p class="hint">Talk to Nova with your voice or type below. Nova has full PC control and is your personal coding agent in any language.</p>
      
      <div class="workspace-bar">
        <span>📁 Workspace:</span>
        <span class="workspace-path">${esc(state.workspace || "workspace")}</span>
        <button class="btn" id="btnOpenWs">Open Folder</button>
      </div>

      <div class="skills-grid">
        <div class="skill-cat">
          <h3>🎙️ Full PC Voice Control</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Open any app or program</b>
              <span>“Open VS Code”, “Open Chrome”, “Open Task Manager”</span>
              <code>OPEN_APP: name</code>
            </div>
            <div class="skill-item">
              <b>Close running apps</b>
              <span>“Close Chrome”, “Exit notepad”, “Kill Spotify”</span>
              <code>CLOSE_APP: name</code>
            </div>
            <div class="skill-item">
              <b>Volume & Mute</b>
              <span>“Volume up”, “Volume down”, “Set volume 50%”, “Mute”</span>
              <code>VOLUME: up/down/50%</code>
            </div>
            <div class="skill-item">
              <b>Media playback</b>
              <span>“Pause music”, “Play”, “Next song”, “Previous track”</span>
              <code>MEDIA: play/pause/next</code>
            </div>
            <div class="skill-item">
              <b>Screenshot</b>
              <span>“Take a screenshot” (captures desktop & opens file)</span>
              <code>SCREENSHOT</code>
            </div>
            <div class="skill-item">
              <b>System & Hardware</b>
              <span>“Check PC specs”, “CPU and RAM usage”, “Lock PC”, “Sleep”, “Empty recycle bin”, “Shutdown in 1 min”</span>
              <code>SYSTEM: stats/lock/sleep</code>
            </div>
            <div class="skill-item">
              <b>Terminal & Shell</b>
              <span>“Run powershell Get-Date”, “Run cmd ipconfig”</span>
              <code>CMD / POWERSHELL</code>
            </div>
          </div>
        </div>

        <div class="skill-cat">
          <h3>💻 Autonomous Coding Agent</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Write code files</b>
              <span>“Write a Python script to fetch Bitcoin price”</span>
              <code>WRITE_FILE: path | code</code>
            </div>
            <div class="skill-item">
              <b>Execute & test code</b>
              <span>“Run script.py”, “Run this code and tell me the output”</span>
              <code>RUN_CODE: python | code</code>
            </div>
            <div class="skill-item">
              <b>Build full apps & websites</b>
              <span>“Create a weather dashboard HTML/CSS/JS in workspace”</span>
              <code>WRITE_FILE + RUN_CODE</code>
            </div>
            <div class="skill-item">
              <b>Inspect & debug files</b>
              <span>“Read main.py and fix the bug”, “List files in folder”</span>
              <code>READ_FILE / LIST_FILES</code>
            </div>
            <div class="skill-item">
              <b>Package management</b>
              <span>“Install requests using pip”, “Run npm install”</span>
              <code>CMD: pip install ...</code>
            </div>
            <div class="skill-item">
              <b>Git Version Control</b>
              <span>“Check git status”, “Commit changes with message updated UI”</span>
              <code>GIT: command</code>
            </div>
          </div>
        </div>

        <div class="skill-cat full-width">
          <h3>🌐 Speak in ANY Language</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Native Multilingual Voice & Speech</b>
              <span>Speak to Nova in English, বাংলা (Bengali), हिंदी (Hindi), اردو (Urdu), Español, Français, Deutsch, العربية, etc.</span>
              <span>Nova recognizes your language, speaks back fluently in that language, and automatically switches speech synthesis voices!</span>
              <code>Auto Multilingual Voice & Speech Detection</code>
            </div>
          </div>
        </div>

        <div class="skill-cat full-width">
          <h3>👁️ Desktop Vision & Multimodal Understanding</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Analyze Desktop Screen</b>
              <span>“What is on my screen?”, “Look at my code on screen and tell me what the bug is”, “Check this UI design”</span>
              <code>VISION: question  /  SCREEN_ANALYZE: question</code>
            </div>
          </div>
        </div>

        <div class="skill-cat">
          <h3>🧠 Second Brain & Semantic Notes</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Save rich notes & knowledge</b>
              <span>“Save a note titled Backend Architecture with contents...”</span>
              <code>NOTE: title | content</code>
            </div>
            <div class="skill-item">
              <b>Semantic BM25 search</b>
              <span>“Search my notes for SQLite schema”, “Find my project ideas”</span>
              <code>SEARCH_NOTES: query</code>
            </div>
          </div>
        </div>

        <div class="skill-cat">
          <h3>⏰ Proactive Scheduling & Hardware Watchdog</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Morning Daily Briefing</b>
              <span>“Give me my morning briefing” (weather via wttr.in, top world news, daily schedule, PC status)</span>
              <code>BRIEFING</code>
            </div>
            <div class="skill-item">
              <b>Natural Timers & Reminders</b>
              <span>“Remind me in 15 minutes to call David”, “Set a timer for 5m”</span>
              <code>REMIND: delay | message  /  TIMER: 10m</code>
            </div>
          </div>
        </div>

        <div class="skill-cat full-width">
          <h3>🌐 Nova Browser (Dedicated Private Browser & DOM Automation)</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Smart Tab Navigation (Never opens duplicate tabs)</b>
              <span>“Open YouTube in Nova Browser”, “Open github.com”, “Switch to Wikipedia tab”</span>
              <code>BROWSER_OPEN / BROWSER_TABS / BROWSER_ACTIVATE / BROWSER_CLOSE</code>
            </div>
            <div class="skill-item">
              <b>Interactive DOM Actions: Click, Type & Scroll</b>
              <span>“Click the search button”, “Type python in the search box”, “Scroll down the page”</span>
              <code>BROWSER_CLICK / BROWSER_TYPE / BROWSER_SCROLL</code>
            </div>
            <div class="skill-item">
              <b>Web Research & Page Content Reader</b>
              <span>“Read this open page and summarize it for me”, “Research latest news in Nova Browser”</span>
              <code>BROWSER_RESEARCH: query or url</code>
            </div>
            <div class="skill-item">
              <b>Persistent Logins: YouTube, WhatsApp Web & Telegram Web</b>
              <span>Log in once, sessions are permanently saved in private profile. Nova can search/play YouTube, message on WhatsApp, and open Telegram!</span>
              <code>BROWSER_YOUTUBE / BROWSER_WHATSAPP / BROWSER_TELEGRAM</code>
            </div>
          </div>
        </div>

        <div class="skill-cat full-width">
          <h3>🔍 Web, Entertainment & Memory</h3>
          <div class="skill-items">
            <div class="skill-item">
              <b>Web & YouTube</b>
              <span>“Search Google for latest AI models”, “Play Interstellar on YouTube”, “Open github.com”</span>
              <code>SEARCH / PLAY / OPEN_URL</code>
            </div>
            <div class="skill-item">
              <b>Long-term Memory</b>
              <span>“Remember that I am building a React app”, “Forget that...”</span>
              <code>REMEMBER / FORGET</code>
            </div>
          </div>
        </div>
      </div>`;

    if ($("#btnOpenWs")) {
      $("#btnOpenWs").onclick = async () => {
        await api("/api/workspace/open");
      };
    }
  }
  if (name === "settings") {
    const c = state.config;
    body.innerHTML = `<h2>Settings</h2>
      <label>AI provider</label><select id="prov"><option value="anthropic">Anthropic (Claude)</option><option value="gemini">Google Gemini</option><option value="openai">OpenAI-compatible (OpenAI, OpenRouter, Groq…)</option><option value="ollama">Ollama / LM Studio (local, free)</option></select>
      <label>API key ${c.has_key ? "(saved — leave blank to keep)" : ""}</label><input id="key" type="password" placeholder="${c.has_key ? "••••••••" : "paste your key"}">
      <label>Model</label><input id="model" value="${esc(c.model)}">
      <label>Base URL (OpenAI-compatible only)</label><input id="base" value="${esc(c.base_url)}">
      <label>Your name</label><input id="uname" value="${esc(c.user_name)}">
      <label>Speech language (e.g. en-US, en-GB, ur-PK, hi-IN)</label><input id="lang" value="${esc(c.language)}">
      <label>LLM Read Timeout (seconds, max 90s; total wait with retry is kept under 100s)</label><input id="llmTimeout" type="number" min="5" max="90" value="${c.llm_timeout || 60}">

      <h3>Voice Customization & Speech Tuning</h3>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px;">
        <div>
          <label>Speaking Rate: <span id="lblRate">${c.voice_rate != null ? c.voice_rate : 1.0}x</span></label>
          <input id="vrate" type="range" min="0.7" max="1.5" step="0.05" value="${c.voice_rate != null ? c.voice_rate : 1.0}" style="width:100%">
        </div>
        <div>
          <label>Voice Pitch: <span id="lblPitch">${c.voice_pitch != null ? c.voice_pitch : 1.0}</span></label>
          <input id="vpitch" type="range" min="0.6" max="1.4" step="0.05" value="${c.voice_pitch != null ? c.voice_pitch : 1.0}" style="width:100%">
        </div>
      </div>
      <div style="margin-bottom:14px;">
        <label>Voice Volume: <span id="lblVol">${Math.round((c.voice_volume != null ? c.voice_volume : 1.0) * 100)}%</span></label>
        <input id="vvol" type="range" min="0.1" max="1.0" step="0.05" value="${c.voice_volume != null ? c.voice_volume : 1.0}" style="width:100%">
        <button class="btn" id="btnTestVoice" style="margin-top:6px; padding:3px 10px; font-size:11px;">Test Voice Sample</button>
      </div>

      <h3>Voice Interaction Modes</h3>
      <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:16px;">
        <label style="display:flex; align-items:center; gap:8px; text-transform:none; font-size:12px; color:#cfe9f5; cursor:pointer">
          <input type="checkbox" id="chkWake" ${c.wake_word_enabled !== false ? 'checked' : ''} style="width:auto">
          <span>Enable <b>'Hey Nova'</b> & <b>'Jarvis'</b> Voice Wake-Word</span>
        </label>
        <label style="display:flex; align-items:center; gap:8px; text-transform:none; font-size:12px; color:#cfe9f5; cursor:pointer">
          <input type="checkbox" id="chkBarge" ${c.barge_in_enabled === true ? 'checked' : ''} style="width:auto">
          <span>Allow interrupting Nova by voice (use headphones)</span>
        </label>
        <label style="display:flex; align-items:center; gap:8px; text-transform:none; font-size:12px; color:#cfe9f5; cursor:pointer">
          <input type="checkbox" id="chkOutsideWs" ${c.allow_outside_workspace === true ? 'checked' : ''} style="width:auto">
          <span>Allow Nova to access files outside workspace (Project Root / PC)</span>
        </label>
      </div>

            <h3>Budget & Multi-Channel Gateways</h3>
      <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:16px;">
        <label>Monthly Budget Cap (USD, 0 for unlimited)</label>
        <input id="monthlyBudget" type="number" step="0.5" min="0" value="${c.monthly_budget_usd != null ? c.monthly_budget_usd : 0}">
        <label style="display:flex; align-items:center; gap:8px; text-transform:none; font-size:12px; color:#cfe9f5; cursor:pointer">
          <input type="checkbox" id="chkDiscord" ${c.discord_enabled === true ? 'checked' : ''} style="width:auto">
          <span>Enable <b>Discord Remote Gateway</b></span>
        </label>
        <label>Discord Bot Token ${c.discord_bot_token_set ? "(saved — leave blank to keep)" : ""}</label>
        <input id="discordToken" type="password" placeholder="${c.discord_bot_token_set ? "••••••••" : "Bot token"}" value="">
        <label>Discord Channel IDs (comma-separated)</label>
        <input id="discordChannels" placeholder="e.g. 123456789012345678" value="${esc((c.discord_channel_ids || []).join(', '))}">
        <label>Discord Allowed User IDs (comma-separated; empty = nobody allowed)</label>
        <input id="discordUsers" placeholder="e.g. 987654321098765432" value="${esc((c.discord_allowed_user_ids || []).join(', '))}">
      </div>

      <div id="settingsError" class="hidden" style="color:#ff4757; background:rgba(255,71,87,0.12); border:1px solid #ff4757; padding:8px 10px; border-radius:4px; margin:8px 0; font-size:12px; font-weight:600;"></div>
      <br><button class="btn" id="save">Save Settings</button>
      ${c.has_key ? ' <button class="btn" id="clearkey" style="color:#ff6b81">Remove saved key</button>' : ""}
      <button class="btn" id="reset">Clear chat history</button>
      <button class="btn" id="exitApp" style="color:#ff6b81">Exit Nova AI</button>
      <p class="hint">Your key is saved only in data/config.json on this PC and sent only to your chosen provider.</p>`;
    $("#prov").value = c.provider === "openai" ? (/generativelanguage/.test(c.base_url) ? "gemini" : /11434|1234/.test(c.base_url) ? "ollama" : "openai") : c.provider;
    $("#prov").onchange = () => { const p = state.presets[$("#prov").value]; if (p) { $("#model").value = p.model; $("#base").value = p.base_url; } };

    $("#vrate").oninput = () => { $("#lblRate").textContent = $("#vrate").value + "x"; };
    $("#vpitch").oninput = () => { $("#lblPitch").textContent = $("#vpitch").value; };
    $("#vvol").oninput = () => { $("#lblVol").textContent = Math.round($("#vvol").value * 100) + "%"; };
    $("#btnTestVoice").onclick = () => {
      state.config.voice_rate = Number($("#vrate").value);
      state.config.voice_pitch = Number($("#vpitch").value);
      state.config.voice_volume = Number($("#vvol").value);
      speak("Greetings! This is how Nova AI sounds with your current voice settings.");
    };

    $("#save").onclick = async () => {
      const errEl = $("#settingsError");
      if (errEl) {
        errEl.textContent = "";
        errEl.classList.add("hidden");
      }
      let prov = $("#prov").value; if (prov === "ollama" || prov === "gemini") prov = "openai";
      const rawBudget = $("#monthlyBudget") ? String($("#monthlyBudget").value).trim() : "0";
      const parsedBudget = rawBudget === "" ? 0 : Number(rawBudget);
      const payload = {
        provider: prov,
        api_key: $("#key").value,
        model: $("#model").value,
        base_url: $("#base").value,
        user_name: $("#uname").value,
        monthly_budget_usd: Number.isNaN(parsedBudget) ? rawBudget : parsedBudget,
        discord_enabled: $("#chkDiscord")?.checked || false,
        discord_bot_token: $("#discordToken")?.value || "",
        discord_channel_ids: ($("#discordChannels")?.value || "").split(",").map(s => s.trim()).filter(Boolean),
        discord_allowed_user_ids: ($("#discordUsers")?.value || "").split(",").map(s => s.trim()).filter(Boolean),
        language: $("#lang").value,
        voice_rate: Number($("#vrate").value),
        voice_pitch: Number($("#vpitch").value),
        voice_volume: Number($("#vvol").value),
        wake_word_enabled: $("#chkWake").checked,
        barge_in_enabled: $("#chkBarge").checked,
        allow_outside_workspace: $("#chkOutsideWs") ? $("#chkOutsideWs").checked : false,
        llm_timeout: Math.max(5, Math.min(90, Number($("#llmTimeout") ? $("#llmTimeout").value : 60) || 60))
      };
      let res;
      try {
        res = await api("/api/config", payload);
      } catch (e) {
        res = { ok: false, error: e.message || "Network error while saving settings." };
      }
      if (!res || res.ok === false || res.error) {
        const msg = (res && res.error) ? res.error : "Failed to save settings.";
        if (errEl) {
          errEl.textContent = msg;
          errEl.classList.remove("hidden");
        }
        showToast("Settings Error", msg, "alert");
        return;
      }
      if (res && res.need_confirm) {
        showConfirmModal({
          action: "SECURITY_SETTINGS",
          prompt: res.prompt || "Security settings change requires confirmation:",
          preview: `Modifying: ${res.keys ? res.keys.join(", ") : "protected configuration keys"}`,
          callback: async (approve) => {
            if (approve) {
              const res2 = await api("/api/config", { ...payload, confirm_token: res.token });
              if (!res2 || res2.ok === false || res2.error) {
                const msg2 = (res2 && res2.error) ? res2.error : "Failed to save security settings.";
                if (errEl) {
                  errEl.textContent = msg2;
                  errEl.classList.remove("hidden");
                }
                showToast("Settings Error", msg2, "alert");
                return;
              }
              await loadState();
              $("#panel").classList.add("hidden");
              showToast("Settings Saved", "Security configuration updated.", "normal");
            } else {
              showToast("Cancelled", "Settings change was cancelled.", "warning");
            }
          }
        });
        return;
      }
      await loadState(); $("#panel").classList.add("hidden");
    };
    if ($("#clearkey")) {
      $("#clearkey").onclick = async () => {
        await api("/api/config", { clear_key: true });
        await loadState();
        renderPanel("settings");
      };
    }
    $("#reset").onclick = async () => {
      await api("/api/reset", { mode: ModeManager.current });
      subtitle("", "");
      if ($("#actionHud")) $("#actionHud").classList.add("hidden");
      $("#panel").classList.add("hidden");
      showToast("History Cleared", "Chat context reset.", "info");
    };
    if ($("#exitApp")) {
      $("#exitApp").onclick = async () => {
        if (confirm("Shut down Nova AI? This will close the background server.")) {
          try { await api("/api/exit", {}); } catch {}
          window.close();
        }
      };
    }
  }
}

/* ---------- News ---------- */
async function loadNews() {
  try {
    const items = await api("/api/news");
    $("#news").innerHTML = items.length ? items.map((n) => `<li><a href="${esc(n.link)}" target="_blank" rel="noopener">${esc(n.title)}</a></li>`).join("") : "<li>No headlines (offline?)</li>";
  } catch { $("#news").innerHTML = "<li>No headlines</li>"; }
}
loadNews(); setInterval(loadNews, 600000);

/* ---------- Globe (decorative wireframe) ---------- */
(function globe() {
  const c = $("#globe"), g = c.getContext("2d"), R = 90, cx = 110, cy = 110;
  let a = 0;
  function draw() {
    g.clearRect(0, 0, 220, 220);
    g.strokeStyle = "rgba(55,214,255,.55)"; g.lineWidth = 1;
    g.beginPath(); g.arc(cx, cy, R, 0, 7); g.stroke();
    for (let lat = -60; lat <= 60; lat += 30) {
      const y = Math.sin((lat * Math.PI) / 180) * R, r = Math.cos((lat * Math.PI) / 180) * R;
      g.beginPath(); g.ellipse(cx, cy + y, r, r * 0.18, 0, 0, 7); g.stroke();
    }
    for (let i = 0; i < 6; i++) {
      const w = Math.abs(Math.cos(a + (i * Math.PI) / 6)) * R;
      g.beginPath(); g.ellipse(cx, cy, w, R, 0, 0, 7); g.stroke();
    }
    a += 0.01; requestAnimationFrame(draw);
  }
  draw();
})();

/* ---------- Particle core ---------- */
(function core() {
  const cv = $("#core"), g = cv.getContext("2d");
  let W, H, pts = [];
  const N = 1100;
  for (let i = 0; i < N; i++) {
    const u = Math.random() * 2 - 1, t = Math.random() * Math.PI * 2, s = Math.sqrt(1 - u * u);
    pts.push({ x: s * Math.cos(t), y: u, z: s * Math.sin(t), p: Math.random() * 6.28 });
  }
  function resize() { W = cv.width = innerWidth; H = cv.height = innerHeight; }
  addEventListener("resize", resize); resize();
  let rot = 0, t0 = 0;
  function frame(t) {
    t0 = t / 1000;
    const target = { idle: 0.08, listening: 0.35, thinking: 0.6, speaking: 0.9 }[mode];
    level += (target - level) * 0.05;
    const pulse = mode === "speaking" ? 0.5 + 0.5 * Math.sin(t0 * 14) * Math.sin(t0 * 5.3) : 0;
    const base = Math.min(W, H) * 0.24;
    g.clearRect(0, 0, W, H);
    rot += 0.003 + level * 0.012;
    const cr = Math.cos(rot), sr = Math.sin(rot);
    const isCyber = ModeManager.isCyber;
    const hue = isCyber
      ? (mode === "thinking" ? 0 : mode === "listening" ? 345 : 355)
      : (mode === "thinking" ? 45 : mode === "listening" ? 150 : 195);
    for (const p of pts) {
      const wob = 1 + level * 0.18 * Math.sin(t0 * 3 + p.p * 3) + pulse * 0.12;
      let x = (p.x * cr - p.z * sr) * wob, z = (p.x * sr + p.z * cr) * wob, y = p.y * wob;
      const k = 1 / (1.8 - z * 0.5);
      const sx = W / 2 + x * base * k * 1.4, sy = H / 2 + y * base * k * 1.4;
      const a = 0.25 + (z + 1) * 0.35;
      g.fillStyle = `hsla(${hue},100%,65%,${a})`;
      g.fillRect(sx, sy, 1.6 * k + 0.6, 1.6 * k + 0.6);
    }
    const grd = g.createRadialGradient(W / 2, H / 2, 0, W / 2, H / 2, base * 1.2);
    grd.addColorStop(0, `hsla(${hue},100%,60%,${0.05 + level * 0.12})`); grd.addColorStop(1, "transparent");
    g.fillStyle = grd; g.fillRect(0, 0, W, H);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();

/* ---------- Commands sent from the phone ---------- */
let lastEvent = null;
async function handlePhone(ev) {
  if (ev.actions && ev.actions.some((a) => a.skill === "REMEMBER" || a.skill === "FORGET")) loadState();
  subtitle("📱 " + ev.text, ev.reply);
  keepReply = true;
  if (!active || mode === "thinking" || mode === "speaking") return; // just show it
  if (rec) { try { rec.abort(); } catch {} rec = null; }
  setMode("speaking");
  await speak(ev.reply);
  setMode("idle");
  scheduleListen(100);
}
async function pollEvents() {
  try {
    const r = await api("/api/events?after=" + (lastEvent == null ? 0 : lastEvent));
    if (lastEvent == null) {
      lastEvent = r.last; // first poll: skip history
    } else {
      for (const ev of r.events) {
        lastEvent = ev.id;
        if (ev.type === "plan_paused") {
          if (ev.pending_info && ev.pending_info.id) {
            showConfirmModal(ev.pending_info);
          } else if (ev.pending_id) {
            showConfirmModal({
              id: ev.pending_id,
              action: ev.paused_step || "PLAN_STEP",
              prompt: `Step '${ev.paused_step}' requires confirmation:`,
              preview: ev.title || "Plan step awaiting approval"
            });
          }
        }
        await handlePhone(ev);
      }
    }
  } catch {}
  setTimeout(pollEvents, 1500);
}
pollEvents();

loadState().then(() => { if (!state.config.has_key) subtitle("", "Open Settings and add your AI key to begin."); });
setMode("idle");


/* ---------- Agent activity monitor ----------
   Polls /api/activity so you always see if the agent is working, what it is
   doing, and for how long. Shows a warning colour if one step runs > 60s. */
(function agentMonitor() {
  const badge = document.getElementById("agentBadge");
  const text = document.getElementById("agentText");
  const timer = document.getElementById("agentTimer");
  const panel = document.getElementById("agentDetail");
  if (!badge) return;
  let snap = null, snapAt = 0, offline = false;
  const STUCK_SECS = 60;
  const fmt = (n) => {
    n = Math.max(0, Math.floor(n));
    const m = Math.floor(n / 60), s = n % 60;
    return m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
  };
  const label = { thinking: "AI THINKING", running: "RUNNING", summarizing: "SUMMARIZING" };

  const baseBadge = "flex items-center gap-2 text-[11px] tracking-[0.18em] px-3 py-1.5 rounded border cursor-pointer select-none max-w-[46vw] backdrop-blur-md transition-all";

  function render() {
    if (offline) {
      badge.className = `${baseBadge} border-[#ff6b81] text-[#ff6b81] bg-[#ff6b81]/10`;
      text.textContent = "SERVER NOT REACHABLE";
      timer.textContent = "";
      return;
    }
    if (!snap || !snap.busy) {
      badge.className = `${baseBadge} border-[#7fa6b8]/35 text-[#7fa6b8] bg-[#030e18]/60 hover:border-[#37d6ff]/60`;
      text.textContent = "AGENT IDLE";
      timer.textContent = "";
      if (snap && snap.last && Date.now() - snap.last.finished * 1000 < 8000) {
        text.textContent = snap.last.ok ? `DONE IN ${fmt(snap.last.secs)}` : "LAST RUN FAILED";
        if (!snap.last.ok) badge.className = `${baseBadge} border-[#ff6b81] text-[#ff6b81] bg-[#ff6b81]/10`;
      }
    } else {
      const drift = (Date.now() - snapAt) / 1000;       // keep timer ticking between polls
      const job = snap.jobs.reduce((a, b) => (b.elapsed > a.elapsed ? b : a));
      const phaseEl = job.phase_elapsed + drift;
      const total = job.elapsed + drift;
      const extra = snap.jobs.length > 1 ? ` (+${snap.jobs.length - 1})` : "";
      const isStuck = phaseEl > STUCK_SECS;
      const isRunning = job.phase === "running";
      badge.className = isStuck
        ? `${baseBadge} border-[#ff6b81] text-[#ff6b81] bg-[#ff6b81]/10 animate-pulse`
        : (isRunning
            ? `${baseBadge} border-[#4dffb0] text-[#4dffb0] bg-[#4dffb0]/10 shadow-[0_0_16px_rgba(77,255,176,0.25)]`
            : `${baseBadge} border-[#ffd24d] text-[#ffd24d] bg-[#ffd24d]/10 shadow-[0_0_16px_rgba(255,210,77,0.25)]`);
      text.textContent = `${label[job.phase] || "WORKING"}${extra}` + (job.detail && job.phase === "running" ? " · " + job.detail : "");
      timer.textContent = fmt(total);
    }
    if (!panel.classList.contains("hidden")) renderPanel();
  }

  function renderPanel() {
    let h = "";
    if (snap && snap.busy) {
      h += "<h5 class='my-2 text-[10px] tracking-widest text-[#37d6ff] uppercase font-bold'>Working now</h5>";
      for (const j of snap.jobs) {
        const d = (Date.now() - snapAt) / 1000;
        h += `<div class="flex justify-between items-center gap-2 py-1 border-b border-[#37d6ff]/10 text-xs"><span class="truncate">${esc(j.source.toUpperCase())}: ${esc(j.task)}</span><span class="text-[#7fa6b8] font-mono shrink-0">${fmt(j.elapsed + d)}</span></div>`;
        h += `<div class="flex justify-between items-center gap-2 py-1 border-b border-[#37d6ff]/10 text-xs"><span class="truncate">↳ ${esc(label[j.phase] || j.phase)}${j.detail ? " · " + esc(j.detail) : ""}</span><span class="text-[#7fa6b8] font-mono shrink-0">${fmt(j.phase_elapsed + d)}</span></div>`;
        for (const s of j.steps) h += `<div class="flex justify-between items-center gap-2 py-1 border-b border-[#37d6ff]/10 text-xs"><span class="text-[#4dffb0] truncate font-mono">✓ ${esc(s.skill)} ${esc(s.arg)}</span><span class="text-[#7fa6b8] font-mono shrink-0">${s.secs}s</span></div>`;
      }
    } else {
      h += "<h5 class='my-2 text-[10px] tracking-widest text-[#37d6ff] uppercase font-bold'>Agent is idle</h5>";
    }
    const hist = (snap && snap.history) || [];
    if (hist.length) {
      h += "<h5 class='my-2 text-[10px] tracking-widest text-[#37d6ff] uppercase font-bold'>Recent runs</h5>";
      for (const r of hist.slice().reverse()) {
        h += `<div class="flex justify-between items-center gap-2 py-1 border-b border-[#37d6ff]/10 text-xs"><span class="${r.ok ? "text-[#4dffb0]" : "text-[#ff6b81]"} truncate font-mono">${r.ok ? "✓" : "✗"} ${esc(r.task || "(task)")}${r.error ? " – " + esc(r.error) : ""}</span><span class="text-[#7fa6b8] font-mono text-[11px] shrink-0">${fmt(r.secs)} · ${r.steps} step${r.steps === 1 ? "" : "s"}</span></div>`;
      }
    }
    panel.innerHTML = h;
  }

  async function poll() {
    try {
      const r = await fetch("/api/activity", { cache: "no-store", headers: { "X-Nova-Token": getSessionToken() } });
      snap = await r.json(); snapAt = Date.now(); offline = false;
    } catch { offline = true; }
    render();
    setTimeout(poll, snap && snap.busy ? 700 : 2000);
  }

  badge.onclick = () => { panel.classList.toggle("hidden"); if (!panel.classList.contains("hidden")) renderPanel(); };
  setInterval(render, 250);   // smooth timer
  poll();
})();

/* ---------- Screen Vision & Spotlight Quick Summon ---------- */
if ($("#btnVision")) {
  $("#btnVision").onclick = async () => {
    setMode("thinking");
    subtitle("Looking at screen...", "Capturing and analyzing desktop visually with Vision AI...");
    playChime("activate");
    try {
      const res = await api("/api/vision/analyze", { question: "What is currently visible on my screen? Provide a concise summary and highlight any errors or key details." });
      const txt = res.analysis || "Screen analysis completed.";
      subtitle("Desktop Vision Result", txt);
      playChime("success");
      await speak(txt.slice(0, 300));
    } catch (e) {
      subtitle("Vision Error", "Could not analyze screen.");
      playChime("alert");
    }
    setMode("idle");
  };
}

window.openSpotlight = () => {
  const modal = $("#spotlightModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  const input = $("#spotlightInput");
  if (input) { input.value = ""; input.focus(); }
  playChime("activate");
};
window.closeSpotlight = () => {
  const modal = $("#spotlightModal");
  if (modal) modal.classList.add("hidden");
};

window.addEventListener("keydown", (e) => {
  const confirmModal = $("#confirmModal");
  if (confirmModal && !confirmModal.classList.contains("hidden")) {
    if (e.key === "Enter") {
      e.preventDefault();
      resolveConfirmation(true);
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      resolveConfirmation(false);
      return;
    }
  }
  if ((e.ctrlKey && e.code === "Space") || (e.altKey && e.code === "KeyK")) {
    e.preventDefault();
    const modal = $("#spotlightModal");
    if (modal && !modal.classList.contains("hidden")) closeSpotlight();
    else openSpotlight();
  } else if (e.key === "Escape") {
    closeSpotlight();
  }
});

if ($("#spotlightInput")) {
  $("#spotlightInput").onkeydown = async (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      const val = $("#spotlightInput").value.trim();
      closeSpotlight();
      if (val) send(val);
    }
  };
}

document.querySelectorAll(".spot-item").forEach(item => {
  item.onclick = () => {
    const act = item.dataset.act;
    closeSpotlight();
    if (act === "vision" && $("#btnVision")) $("#btnVision").click();
    else if (act === "briefing") send("Give me my morning briefing");
    else if (act === "stats") send("Check PC specs, CPU, RAM and hardware stats");
    else if (act === "browser") openPanel("browser");
    else if (act === "doctor") openPanel("doctor");
    else if (act === "usage") openPanel("usage");
    else if (act === "plan") {
      $("#text").value = "Create a plan to: ";
      $("#text").focus();
    }
  };
});



/* ---------- Confirmation Gate Modal ---------- */
let currentPendingAction = null;
let pendingConfirmId = null;
let isConfirming = false;

function closeModal() {
  const modal = $("#confirmModal");
  if (modal) modal.classList.add("hidden");
  const allowBtn = $("#confirmAllowBtn");
  const denyBtn = $("#confirmDenyBtn");
  if (allowBtn) allowBtn.disabled = false;
  if (denyBtn) denyBtn.disabled = false;
}

function showConfirmModal(pending) {
  currentPendingAction = pending;
  pendingConfirmId = pending ? (pending.id || null) : null;
  isConfirming = false;
  const modal = $("#confirmModal");
  if (!modal) return;
  const allowBtn = $("#confirmAllowBtn");
  const denyBtn = $("#confirmDenyBtn");
  if (allowBtn) allowBtn.disabled = false;
  if (denyBtn) denyBtn.disabled = false;
  const promptEl = $("#confirmPrompt");
  const previewEl = $("#confirmPreview");
  if (promptEl) promptEl.textContent = pending.prompt || "A high-impact action requires confirmation:";
  if (previewEl) previewEl.textContent = `${pending.action}: ${pending.preview || ""}`;
  modal.classList.remove("hidden");
}

async function resolveConfirmation(approve) {
  if (isConfirming || (!currentPendingAction && !pendingConfirmId)) return;
  isConfirming = true;
  const allowBtn = $("#confirmAllowBtn");
  const denyBtn = $("#confirmDenyBtn");
  if (allowBtn) allowBtn.disabled = true;
  if (denyBtn) denyBtn.disabled = true;

  const action = currentPendingAction;
  const confirmId = pendingConfirmId || (action ? action.id : null);
  currentPendingAction = null;
  pendingConfirmId = null;
  closeModal();

  if (!action && !confirmId) {
    isConfirming = false;
    return;
  }

  if (action && action.callback) {
    try {
      await action.callback(approve);
    } finally {
      isConfirming = false;
    }
    return;
  }
  try {
    const res = await api("/api/confirm", { id: confirmId || (action && action.id), approve: approve });
    const actionName = (action && action.action) ? action.action : "Action";
    if (approve) {
      showToast("Action Approved", `${actionName} completed.`, "success");
      if (res.result) {
        subtitle("", `Executed ${actionName}: ${res.result.slice(0, 100)}`);
        if (active && !micMuted) speak(`Executed ${actionName}`);
      }
    } else {
      showToast("Action Denied", `${actionName} cancelled.`, "info");
      subtitle("", `Cancelled ${actionName}.`);
    }
  } catch (err) {
    showToast("Confirmation Error", err.message || "Failed to confirm", "error");
  } finally {
    isConfirming = false;
  }
}

if ($("#confirmAllowBtn")) $("#confirmAllowBtn").onclick = () => resolveConfirmation(true);
if ($("#confirmDenyBtn")) $("#confirmDenyBtn").onclick = () => resolveConfirmation(false);
if ($("#confirmCancelPlanBtn")) {
  $("#confirmCancelPlanBtn").onclick = async () => {
    try {
      const res = await api("/api/plan/cancel", {});
      closeModal();
      showToast("Plan Cancelled", res.message || "Plan cancelled.", "info");
      subtitle("", "Plan cancelled.");
    } catch (err) {
      showToast("Error", err.message || "Failed to cancel plan", "error");
    }
  };
}

// Initialize Mode Manager
ModeManager.init();
