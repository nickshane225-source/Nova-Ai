/* Nova Remote: the phone page. Sends your commands to Nova on the PC and shows the answers. */
(function () {
  const $ = (s) => document.querySelector(s);
  const log = $("#log");

  /* ---- pairing token (comes from the QR code link) ---- */
  const params = new URLSearchParams(location.search);
  let token = params.get("t") || "";
  try {
    if (token) { localStorage.setItem("nova_t", token); history.replaceState(null, "", location.pathname); }
    else token = localStorage.getItem("nova_t") || "";
  } catch {}

  let info = { name: "Nova", apps: [], language: "en-US" };
  let paired = false;

  /* ---- mode management (Developer vs Cyber) ---- */
  let currentMode = "developer";
  try {
    currentMode = localStorage.getItem("nova_remote_mode") === "cyber" ? "cyber" : "developer";
  } catch {}

  function applyMode() {
    const isCyber = currentMode === "cyber";
    document.body.classList.toggle("cyber-mode", isCyber);
    const btn = $("#btnMode");
    if (btn) {
      btn.textContent = isCyber ? "Developer Mode" : "Cyber Mode";
      btn.title = isCyber ? "Switch to Developer Mode" : "Switch to Cyber Mode";
    }
  }
  const modeBtn = $("#btnMode");
  if (modeBtn) {
    modeBtn.onclick = () => {
      currentMode = currentMode === "cyber" ? "developer" : "cyber";
      try { localStorage.setItem("nova_remote_mode", currentMode); } catch {}
      applyMode();
      add("sys", currentMode === "cyber" ? "Switched to Cyber Mode (Nova Cyber)." : "Switched to Developer Mode.");
    };
  }
  applyMode();

  function add(kind, text) {
    const d = document.createElement("div");
    d.className = "msg " + kind;
    d.textContent = text;
    log.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }
  function conn(state, text) {
    $("#conn").className = state;
    $("#connText").textContent = text;
  }

  async function api(path, body) {
    const opt = { headers: { "X-Nova-Token": token } };
    if (body) { opt.method = "POST"; opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
    let r;
    try { r = await fetch(path, opt); } catch { return { _net: true, error: "Can't reach your PC. Is Nova running and are you on the same Wi-Fi?" }; }
    let j = {};
    try { j = await r.json(); } catch {}
    if (r.status === 401 || r.status === 403 || r.status === 429) j._auth = true;
    if (!r.ok && !j.error) j.error = "Error " + r.status;
    return j;
  }

  /* ---- connection / info ---- */
  async function ping(first) {
    if (!token) {
      conn("bad", "Not paired");
      if (first) add("err", "Not paired yet. On your PC open Nova → Mobile and scan the QR code with this phone.");
      return;
    }
    const r = await api("/api/remote/info");
    if (r.error) {
      paired = false;
      conn("bad", r._auth ? "Not paired" : "Offline");
      if (first || r._auth) { if (!ping.warned) add("err", r.error); ping.warned = true; }
      return;
    }
    ping.warned = false;
    paired = true; info = r;
    conn("ok", "Connected to " + (r.name || "Nova"));
    if (first) {
      add("sys", (r.user ? "Hi " + r.user + ". " : "") + "You're controlling " + (r.name || "Nova") + " on your PC. Type a command" + (canVoice() ? " or tap 🎤." : ", or use the 🎤 key on your keyboard to dictate."));
      if (!r.has_key) add("err", "The PC has no AI key yet. Add one in Nova → Settings.");
      renderChips();
    }
  }
  function renderChips() {
    const c = $("#chips"); c.innerHTML = "";
    const items = (info.apps || []).slice(0, 8).map((a) => ["Open " + a, "Open " + a]);
    items.push(["What time is it?", "What time is it?"]);
    items.forEach(([label, cmd]) => {
      const b = document.createElement("button");
      b.type = "button"; b.textContent = label;
      b.onclick = () => send(cmd);
      c.appendChild(b);
    });
  }

  /* ---- sending ---- */
  const ACTION_LABEL = {
    OPEN_APP: "Opened app",
    CLOSE_APP: "Closed app",
    VOLUME: "Volume",
    MEDIA: "Media",
    SCREENSHOT: "Screenshot",
    SYSTEM: "System",
    CMD: "Command",
    POWERSHELL: "PowerShell",
    WRITE_FILE: "Created file",
    READ_FILE: "Read file",
    RUN_CODE: "Executed code",
    LIST_FILES: "List files",
    GIT: "Git",
    OPEN_URL: "Opened link",
    SEARCH: "Searching",
    PLAY: "Playing",
    REMEMBER: "Remembered",
    FORGET: "Forgot",
    NOTE: "Saved note",
    SEARCH_NOTES: "Searched notes",
    DELETE_NOTE: "Deleted note",
    PLAN: "Executed plan",
    GITHUB: "GitHub",
    SMART_HOME: "Smart Home",
    BRIEFING: "Morning briefing",
    TIMER: "Set timer",
    REMIND: "Set reminder",
    SCHEDULE_AUTO: "Scheduled automation",
    LIST_AUTOMATIONS: "List automations",
    CANCEL_AUTOMATION: "Cancelled automation",
    DIAGNOSTICS: "System health",
    USAGE: "Token usage",
    AUDIT: "Security audit",
  };
  let busy = false;
  async function send(text) {
    text = (text || "").trim();
    if (!text || busy) return;
    if (!paired) await ping(false);
    busy = true;
    add("you", text);
    const typing = add("nova", "");
    typing.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
    const r = await api("/api/remote/chat", { message: text, mode: currentMode });
    typing.remove();
    busy = false;
    if (r.error) { add("err", r.error); if (r._auth) conn("bad", "Not paired"); return; }
    add("nova", r.reply);
    (r.actions || []).forEach((a) => {
      const isBad = typeof a.result === "string" && /^(Refused|Error|Failed|Could not|Command timed out)/i.test(a.result);
      const label = ACTION_LABEL[a.skill] || a.skill;
      const detail = a.arg ? a.arg.split("\n")[0].slice(0, 40) : "";
      add("act" + (isBad ? " bad" : ""), (isBad ? "⚠ " : "✓ ") + label + (detail ? ": " + detail : ""));
    });
    speak(r.reply);
  }

  function detectTextLanguage(text) {
    if (!text) return info.language || "en-US";
    if (/[\u0980-\u09FF]/.test(text)) return "bn-BD";
    if (/[\u0900-\u097F]/.test(text)) return "hi-IN";
    if (/[\u0600-\u06FF]/.test(text)) return /[\u067E\u0686\u0698\u06AF\u06BA\u06BE\u06CC]/.test(text) ? "ur-PK" : "ar-SA";
    if (/[\u3040-\u309F\u30A0-\u30FF]/.test(text)) return "ja-JP";
    if (/[\u4E00-\u9FFF]/.test(text)) return "zh-CN";
    if (/[\uAC00-\uD7AF]/.test(text)) return "ko-KR";
    if (/[\u0400-\u04FF]/.test(text)) return "ru-RU";
    if (/^[A-Za-z0-9\s.,!?'"()\-:;/_+=@#$%&*~`^<>{}|[\]\\]+$/.test(text.trim())) return "en-US";
    return info.language || "en-US";
  }

  /* ---- voice out (phone speaker) ---- */
  function speak(text) {
    if (!$("#speakToggle").checked || !("speechSynthesis" in window)) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = detectTextLanguage(text);
      speechSynthesis.speak(u);
    } catch {}
  }
  try { $("#speakToggle").checked = localStorage.getItem("nova_speak") !== "0"; } catch {}
  $("#speakToggle").onchange = (e) => { try { localStorage.setItem("nova_speak", e.target.checked ? "1" : "0"); } catch {} if (!e.target.checked) try { speechSynthesis.cancel(); } catch {} };

  /* ---- voice in ---- */
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function canVoice() { return !!SR && window.isSecureContext; }
  let rec = null;
  $("#mic").onclick = () => {
    if (!canVoice()) {
      add("sys", "Browsers only allow the microphone button on secure (https) pages, and this link is plain http on your Wi-Fi. Easy fix: tap the 🎤 key on your phone keyboard to dictate, then press send.");
      $("#text").focus();
      return;
    }
    if (rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = info.language || "en-US";
    rec.interimResults = true;
    let final = "";
    rec.onstart = () => $("#mic").classList.add("on");
    rec.onresult = (e) => {
      let t = ""; for (const r of e.results) { t += r[0].transcript; if (r.isFinal) final = t; }
      $("#text").value = t;
    };
    rec.onerror = (e) => { if (e.error === "not-allowed") add("err", "Microphone blocked for this page."); };
    rec.onend = () => {
      $("#mic").classList.remove("on"); rec = null;
      const t = ($("#text").value || final).trim();
      if (t) { $("#text").value = ""; send(t); }
    };
    try { rec.start(); } catch { rec = null; }
  };

  $("#form").onsubmit = (e) => {
    e.preventDefault();
    const t = $("#text").value;
    $("#text").value = "";
    send(t);
  };

  ping(true);
  setInterval(() => ping(false), 10000);
})();
