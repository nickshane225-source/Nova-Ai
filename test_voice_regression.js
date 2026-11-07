/**
 * Automated Regression Tests for Nova AI Voice Pipeline
 * Loads and exercises the REAL web/app.js inside a Node.js VM sandbox with mocked browser APIs.
 */

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

console.log("=================================================");
console.log("Nova AI Voice Pipeline Regression Tests (Real app.js)");
console.log("=================================================\n");

function createMockEnvironment() {
  const elements = {};
  function getEl(sel) {
    if (!elements[sel]) {
      elements[sel] = {
        tagName: "DIV",
        className: "",
        style: {},
        classList: {
          add: () => {},
          remove: () => {},
          contains: () => false,
          toggle: () => {},
        },
        addEventListener: () => {},
        removeEventListener: () => {},
        appendChild: () => {},
        setAttribute: () => {},
        getAttribute: () => null,
        focus: () => {},
        click: () => {},
        value: "",
        textContent: "",
        innerHTML: "",
        getContext: () => ({
          clearRect: () => {},
          fillRect: () => {},
          beginPath: () => {},
          arc: () => {},
          ellipse: () => {},
          moveTo: () => {},
          lineTo: () => {},
          fill: () => {},
          stroke: () => {},
          createRadialGradient: () => ({ addColorStop: () => {} }),
          createLinearGradient: () => ({ addColorStop: () => {} }),
        }),
      };
    }
    return elements[sel];
  }

  const mockDoc = {
    querySelector: getEl,
    querySelectorAll: () => [],
    getElementById: (id) => getEl("#" + id),
    createElement: (tag) => getEl(tag),
    body: getEl("body"),
  };

  let recognitionInstances = [];
  class MockSpeechRecognition {
    constructor() {
      this.lang = "en-US";
      this.continuous = true;
      this.interimResults = true;
      recognitionInstances.push(this);
    }
    start() {
      if (this.onstart) this.onstart();
    }
    stop() {
      if (this.onend) this.onend();
    }
    abort() {
      if (this.onend) this.onend();
    }
  }

  const spokenUtterances = [];
  const mockWin = {
    SpeechRecognition: MockSpeechRecognition,
    webkitSpeechRecognition: MockSpeechRecognition,
    speechSynthesis: {
      speaking: false,
      paused: false,
      getVoices: () => [],
      cancel: () => {},
      resume: () => {},
      pause: () => {},
      speak: (u) => {
        spokenUtterances.push(u);
      },
    },
    SpeechSynthesisUtterance: class {
      constructor(text) {
        this.text = text;
      }
    },
    BroadcastChannel: class {
      constructor() {}
      postMessage() {}
      close() {}
    },
    navigator: {
      permissions: { query: async () => ({ state: "granted" }) },
      mediaDevices: {
        getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }),
      },
    },
    location: { pathname: "/", search: "" },
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    addEventListener: () => {},
    removeEventListener: () => {},
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
    fetch: async () => ({
      json: async () => ({ config: { language: "en-US", barge_in_enabled: false }, characters: [], memory: [], presets: {} }),
    }),
    innerWidth: 1024,
    innerHeight: 768,
  };
  mockWin.window = mockWin;
  mockWin.document = mockDoc;

  const sandbox = {
    ...mockWin,
    window: mockWin,
    document: mockDoc,
    navigator: mockWin.navigator,
    location: mockWin.location,
    localStorage: mockWin.localStorage,
    speechSynthesis: mockWin.speechSynthesis,
    SpeechSynthesisUtterance: mockWin.SpeechSynthesisUtterance,
    SpeechRecognition: mockWin.SpeechRecognition,
    webkitSpeechRecognition: mockWin.webkitSpeechRecognition,
    BroadcastChannel: mockWin.BroadcastChannel,
    fetch: mockWin.fetch,
    requestAnimationFrame: mockWin.requestAnimationFrame,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    setInterval: setInterval,
    clearInterval: clearInterval,
    console: {
      log: () => {},
      warn: (...args) => sandbox._lastWarn = args.join(" "),
      error: (...args) => sandbox._lastError = args.join(" "),
    },
    Date: Date,
    Math: Math,
    JSON: JSON,
    _lastWarn: "",
    _lastError: "",
  };

  const context = vm.createContext(sandbox);
  const appJsPath = path.resolve(__dirname, "web/app.js");
  const code = fs.readFileSync(appJsPath, "utf8");
  vm.runInContext(code, context);

  const scope = vm.runInContext(
    `({
      get mode() { return mode; },
      set mode(v) { mode = v; },
      get active() { return active; },
      set active(v) { active = v; },
      get rec() { return rec; },
      get abortStreak() { return abortStreak; },
      set abortStreak(v) { abortStreak = v; },
      get state() { return state; },
      setMode,
      cancelSpeech,
      scheduleListen,
      startListening,
      speak
    })`,
    context
  );

  return { context, scope, recognitionInstances, elements, spokenUtterances };
}

// --- TEST 1: cancelSpeech resets mode from speaking to idle ---
(function testCancelSpeech() {
  console.log("--- TEST 1: cancelSpeech() restores mode to 'idle' in real app.js ---");
  const { scope } = createMockEnvironment();
  assert.strictEqual(scope.mode, "idle");
  scope.setMode("speaking");
  assert.strictEqual(scope.mode, "speaking");
  scope.cancelSpeech();
  assert.strictEqual(scope.mode, "idle", "cancelSpeech() must reset mode to 'idle'");
  console.log("[PASS] TEST 1 passed: cancelSpeech() cleanly restores mode to 'idle'.\n");
})();

// --- TEST 2: Abort streak limiter stops after 3 aborts in 3 seconds ---
(function testAbortStreakLimiter() {
  console.log("--- TEST 2: Real app.js abort streak limiter terminates rapid loop ---");
  const { scope, elements } = createMockEnvironment();
  scope.active = true;
  scope.startListening();
  assert(scope.rec, "Recognition session should be active");

  const rec = scope.rec;
  // Simulate 3 rapid aborts
  rec.onerror({ error: "aborted" });
  rec.onerror({ error: "aborted" });
  rec.onerror({ error: "aborted" });

  assert.strictEqual(scope.active, false, "active flag should be set to false after 3 rapid aborts");
  const subText = elements["#subtitle"] ? elements["#subtitle"].textContent : "";
  assert.strictEqual(scope.mode, "idle", "Mode should be idle when mic blocked");
  console.log("[PASS] TEST 2 passed: Real app.js abort streak stopped listener after 3 aborts.\n");
})();

// --- TEST 3: Abort streak resets on recognition result ---
(function testAbortStreakResetOnResult() {
  console.log("--- TEST 3: Abort streak resets when onresult receives recognized speech ---");
  const { scope } = createMockEnvironment();
  scope.active = true;
  scope.startListening();
  const rec = scope.rec;

  // Add 2 aborts
  rec.onerror({ error: "aborted" });
  rec.onerror({ error: "aborted" });
  assert.strictEqual(scope.abortStreak.length, 2);

  // Recognition receives result
  rec.onresult({
    resultIndex: 0,
    results: [
      Object.assign([{ transcript: "hello" }], { isFinal: true })
    ]
  });

  assert.strictEqual(scope.abortStreak.length, 0, "abortStreak should be empty after onresult");
  console.log("[PASS] TEST 3 passed: Abort streak cleared on recognized speech.\n");
})();

// --- TEST 4: Silence handling (no-speech) is silent ---
(function testNoSpeechIsSilent() {
  console.log("--- TEST 4: 'no-speech' is handled silently without error warnings ---");
  const { scope, context } = createMockEnvironment();
  scope.active = true;
  scope.startListening();
  const rec = scope.rec;

  context._lastWarn = "";
  rec.onerror({ error: "no-speech" });
  assert.strictEqual(context._lastWarn, "", "no-speech must not log a console warning");
  console.log("[PASS] TEST 4 passed: 'no-speech' handled silently.\n");
})();

// --- TEST 5: Debounced scheduleListen produces exactly one startListening ---
(function testScheduleListenDebounce() {
  console.log("--- TEST 5: Debounced scheduleListen produces exactly one invocation ---");
  const { scope, recognitionInstances } = createMockEnvironment();
  scope.active = true;
  const initialCount = recognitionInstances.length;

  // Schedule twice back-to-back with different delays
  scope.scheduleListen(80);
  scope.scheduleListen(20);

  setTimeout(() => {
    const afterCount = recognitionInstances.length;
    assert.strictEqual(afterCount - initialCount, 1, "Expected exactly 1 new recognition session created");
    console.log("[PASS] TEST 5 passed: Multiple scheduleListen calls debounced to 1 listener.\n");
    runEchoGuardTest();
  }, 120);
})();

// --- TEST 6: Echo guard suppresses speech start during first 600ms of output ---
function runEchoGuardTest() {
  console.log("--- TEST 6: Echo guard suppresses speech start during first 600ms of playback ---");
  const { scope, context } = createMockEnvironment();
  scope.active = true;
  scope.state.config.barge_in_enabled = true;
  scope.startListening();
  const rec = scope.rec;

  scope.setMode("speaking");
  context.window._speechStartTime = Date.now();

  // Speech detected at 100ms into playback
  rec.onspeechstart();
  assert.strictEqual(scope.mode, "speaking", "Echo guard should ignore speech-start within first 600ms");

  // Speech detected after 700ms
  context.window._speechStartTime = Date.now() - 750;
  rec.onspeechstart();
  assert.strictEqual(scope.mode, "listening", "Barge-in should trigger after 600ms when enabled");
  console.log("[PASS] TEST 6 passed: Echo guard properly shields initial audio playback.\n");

  console.log("=================================================");
  console.log("ALL REAL APP.JS VOICE REGRESSION TESTS PASSED!");
  console.log("=================================================");
  process.exit(0);
}
